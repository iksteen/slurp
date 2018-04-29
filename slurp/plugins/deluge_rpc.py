import asyncio
import base64
import hashlib
import os
import logging
import ssl
import urllib.parse
import zlib
from configparser import NoSectionError

import bencoder
import pyrencode

from slurp.util import key_for_episode, format_episode_info

logger = logging.getLogger(__name__)


class DelugeRpcClientProtocol(asyncio.Protocol):
    def __init__(self, client, *, loop=None):
        self.client = client
        self.loop = loop if loop is not None else asyncio.get_event_loop()
        self.transport = None
        self._id = 0
        self._pending = {}
        self._buffer = bytearray()

    def connection_made(self, transport):
        def on_authenticated(f):
            exc = f.exception()
            if exc is not None:
                try:
                    raise exc
                except:
                    logger.exception('Failed to authenticate to Deluge:')
                    self.client.connection_failed(exc)
            else:
                self.client.connection_made(self)

        self.transport = transport
        f = self.loop.create_task(self.call_remote(
            'daemon.login',
            self.client.username,
            self.client.password
        ))
        f.add_done_callback(on_authenticated)

    def data_received(self, data):
        self._buffer.extend(data)
        d_obj = zlib.decompressobj()
        try:
            message = pyrencode.loads(d_obj.decompress(self._buffer))
        except (ValueError, zlib.error):
            logger.exception('Error while decoding buffer')
            return
        else:
            self._buffer = bytearray(d_obj.unused_data)

        try:
            if message[0] == 1:
                request_id, result = message[1:]
                self._pending.pop(request_id).set_result(result)
            elif message[0] == 2:
                request_id, (err_class, err_msg, err_tb) = message[1:]
                try:
                    raise Exception(err_msg)
                except Exception as e:
                    self._pending.pop(request_id).set_exception(e)
        except:
            logger.exception('Error while processing Deluge RPC repsonse:')

    @property
    def _request_id(self):
        self._id += 1
        return self._id

    async def call_remote(self, method, *args, **kwargs):
        request_id = self._request_id
        self._pending[request_id] = f = self.loop.create_future()
        payload = zlib.compress(pyrencode.dumps([[request_id, method, args, kwargs]]))
        self.transport.write(payload)
        return await f

    def connection_lost(self, exc):
        self.client.connection_lost()
        for d in self._pending.values():
            d.set_exception(exc)


class DelugeRpcClient(object):
    def __init__(self, host, port, username, password, *, loop=None):
        self.loop = loop if loop is not None else asyncio.get_event_loop()
        self._host = host
        self._port = port
        self.username = username
        self.password = password
        self._connector = None
        self._connection = None
        self._connection_fs = None

    async def _get_connection(self):
        if self._connection is not None:
            return self._connection

        f = self.loop.create_future()
        if self._connection_fs is not None:
            self._connection_fs.append(f)
            return await f

        self._connection_fs = [f]
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            self._connector = self.loop.create_task(self.loop.create_connection(
                lambda: DelugeRpcClientProtocol(self, loop=self.loop),
                self._host,
                self._port,
                ssl=ctx,
            ))
            await self._connector
        except Exception as e:
            self.connection_failed(e)

        return await f

    def connection_failed(self, exc):
        fs, self._connection_fs = self._connection_fs, None
        for f in fs:
            f.set_exception(exc)

    def connection_made(self, connection):
        self._connection = connection
        fs, self._connection_fs = self._connection_fs, None
        for f in fs:
            f.set_result(self._connection)

    def connection_lost(self):
        self._connection = None

    async def call_remote(self, method_name, *args, **kwargs):
        conn = await self._get_connection()
        return await conn.call_remote(method_name, *args, **kwargs)

    def disconnect(self):
        if self._connection is not None:
            self._connection.cloase()
        if self._connector is not None:
            self._connector.cancel()


class DelugeRpcDownloadPlugin:
    media = [
        'torrent:url',
        'torrent:magnet',
    ]

    _interval = 10
    _rpc_host = 'localhost'
    _rpc_port = 58846
    _rpc_username = None
    _rpc_password = None
    _seed_limit = 0.0
    _prefer_medium = 'url'

    _pause_counter = 0

    def __init__(self, core, *, loop=None):
        self.core = core
        self.loop = loop if loop is not None else asyncio.get_event_loop()

        self._origin_seed_limit = {}
        self._downloads = {}
        self._torrent_ids = {}

        try:
            with open(os.path.expanduser('~/.config/deluge/auth')) as f:
                for line in f.readlines():
                    username, password, level = line.split(':')
                    if username == 'localclient':
                        self._rpc_username = username
                        self._rpc_password = password
                        break
        except:
            pass

        try:
            section = dict(core.config.items('slurp.download.deluge_rpc'))
            self._interval = int(section.get('interval', self._interval))
            self._rpc_host = section.get('rpc_host', self._rpc_host)
            self._rpc_port = int(section.get('rpc_port', str(self._rpc_port)))
            self._rpc_username = section.get('rpc_username', self._rpc_username)
            self._rpc_password = section.get('rpc_password', self._rpc_password)
            self._seed_limit = float(section.get('seed_limit', self._seed_limit))
            self._prefer_medium = section.get('prefer_medium', self._prefer_medium)
            assert self._prefer_medium in ('url', 'magnet'), 'deluge_rpc option prefer should be url or magnet'
            for key, value in section.items():
                if key.startswith('seed_limit.'):
                    origin = key.split('.', 1)[1]
                    self._origin_seed_limit[origin] = float(value)
        except NoSectionError:
            pass
        except:
            logger.exception('Invalid Deluge RPC download provider configuration:')

        if not self._rpc_username or not self._rpc_password:
            logger.info('Missing Deluge RPC username or password.')
            return

        self._client = DelugeRpcClient(self._rpc_host, self._rpc_port, self._rpc_username, self._rpc_password)

    async def start(self):
        pass

    async def run(self):
        while True:
            try:
                await self._check_downloads()
            except:
                logger.exception('Failed to check downloads:')
            await asyncio.sleep(self._interval, loop=self.loop)

    def is_downloading(self, episode_info):
        return key_for_episode(episode_info) in self._downloads

    async def download(self, episodes_info, data):
        keys = []
        for episode_info in episodes_info:
            logger.info('Downloading {} using Deluge'.format(format_episode_info(episode_info)))
            key = key_for_episode(episode_info)
            self._downloads[key] = None
            keys.append(key)

        seed_limit = self._origin_seed_limit.get(data['origin'], self._seed_limit)
        if seed_limit:
            options = {
                'stop_at_ratio': True,
                'stop_ratio': seed_limit,
            }
        else:
            options = {}

        if self._prefer_medium == 'url':
            media = ('torrent:url', 'torrent:magnet')
        else:
            media = ('torrent:magnet', 'torrent:url')

        for medium in media:
            if medium in data['media']:
                if medium == 'torrent:url':
                    url = data['media']['torrent:url']['url']
                    coro = self._add_torrent_url(url, options)
                else:
                    url = data['media']['torrent:magnet']['magnetURI']
                    coro = self._add_torrent_magnet(url, options)
                break
        else:
            raise RuntimeError('This should never happen')

        try:
            info_hash = await coro
        except:
            logger.exception('Failed to add torrent ({}) to Deluge:'.format(url))
            for key in keys:
                del self._downloads[key]
        else:
            for episode_info in episodes_info:
                self._downloads[key_for_episode(episode_info)] = info_hash
            self._torrent_ids.setdefault(info_hash, []).extend(episodes_info)

            try:
                await self._check_downloads([info_hash])
            except:
                logger.exception('Failed to check download status:')

    async def _add_torrent_url(self, url, options):
        async with self.core.session.get(url) as response:
            body = await response.read()

        parsed_body = bencoder.decode(body)
        info_hash = hashlib.sha1(bencoder.encode(parsed_body[b'info'])).hexdigest()

        await self._client.call_remote(
            'core.add_torrent_file',
            parsed_body[b'info'][b'name'] + b'.torrent',
            base64.b64encode(body),
            options,
        )
        return info_hash

    async def _add_torrent_magnet(self, url, options):
        parsed_magnet = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed_magnet.query)
        for urn in query.get('xt', []):
            if urn.startswith('urn:btih:'):
                info_hash = urn.split(':')[2].lower()
                break
        else:
            raise ValueError('Could not interpret magnet URI: {}'.format(url))

        await self._client.call_remote(
            'core.add_torrent_magnet',
            url,
            options,
        )
        return info_hash

    async def _check_downloads(self, torrent_ids=None):
        async def check_status(torrent_id, status):
            if not status[b'is_finished']:
                return

            episodes_info = self._torrent_ids.pop(torrent_id)

            download_dir = status[b'save_path']
            await self.core.download.download_completed(
                [
                    (
                        os.fsdecode(os.path.join(download_dir, f[b'path'])),
                        f[b'size']
                    )
                    for f in status[b'files']
                ],
            )
            for episode_info in episodes_info:
                del self._downloads[key_for_episode(episode_info)]

        if torrent_ids is None:
            torrent_ids = list(self._torrent_ids.keys())

        if not torrent_ids:
            return

        result = await self._client.call_remote(
            'core.get_torrents_status',
            {'id': torrent_ids},
            ['is_finished', 'save_path', 'files'],
        )

        result = [
            (torrent_id.decode('ascii'), status)
            for torrent_id, status in result.items()
            if status
        ]

        for missing_id in set(torrent_ids) - set(map(lambda r: r[0], result)):
            episodes_info = self._torrent_ids.pop(missing_id)
            for episode_info in episodes_info:
                del self._downloads[key_for_episode(episode_info)]

        return await asyncio.gather(
            *(check_status(torrent_id, status) for torrent_id, status in result),
            loop=self.loop
        )
