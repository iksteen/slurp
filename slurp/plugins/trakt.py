import asyncio
import json
import logging

from slurp.backlog import BacklogItem
from slurp.plugin_types import BackendPlugin, MetadataPlugin

logger = logging.getLogger(__name__)


class UnauthorizedError(Exception):
    pass


class UnknownError(Exception):
    pass


class TraktMetadataPlugin(MetadataPlugin):
    def __init__(self, backend):
        self.backend = backend

    async def start(self):
        pass

    async def run(self):
        pass

    async def enrich(self, backlog_item):
        try:
            result = await self.backend.trakt_request(
                'shows/{slug}/seasons/{season}/episodes/{episode}',
                {
                    'slug': backlog_item.show_id,
                    'season': backlog_item.season,
                    'episode': backlog_item.episode,
                }
            )
        except:
            logger.exception('Failed to retrieve extended episode info:')
        else:
            backlog_item.metadata['episode_title'] = result['title']


class PostProcessorPlugin(object):
    pass


class TraktPostProcessorPlugin(PostProcessorPlugin):
    def __init__(self, backend):
        self.backend = backend

    async def start(self):
        pass

    async def run(self):
        pass

    async def process(self, backlog_items, _):
        episodes = {}
        for backlog_item in backlog_items:
            logger.info('Marking {} completed on trakt.tv'.format(backlog_item))
            episodes.setdefault(
                backlog_item.show_id,
                {}
            ).setdefault(
                backlog_item.season,
                set()
            ).add(
                backlog_item.episode
            )

        try:
            await self.backend.trakt_request(
                'sync/collection',
                None,
                {
                    'shows': [
                        {
                            'ids': {
                                'slug': slug,
                            },
                            'seasons': [
                                {
                                    'number': season,
                                    'episodes': [
                                        {
                                            'number': episode,
                                        }
                                        for episode in episode_list
                                    ],
                                }
                                for season, episode_list in seasons.items()
                            ],
                        }
                        for slug, seasons in episodes.items()
                    ],
                },
            )
        except:
            logger.exception('Failed to mark episodes completed on trakt.tv:')


class TraktBackendPlugin(BackendPlugin):
    username = None
    client_id = None  # For oauth2 access
    client_secret = None  # For oauth2 access
    pin_code = None  # For oauth2 access

    access_token = None
    refresh_token = None

    custom_list = None
    base_url = 'https://api.trakt.tv'
    interval = 3600
    timeout = 30
    replace_title = {}

    _timer = None

    def __init__(self, core, *, loop=None):
        self.core = core
        self.loop = loop if loop is not None else asyncio.get_event_loop()

        self._trakt_sem = asyncio.Semaphore(2)

        section = dict(core.config.items('slurp.backend.trakt'))

        self.username = section['username']

        self.client_id = section['client_id']
        self.client_secret = section['client_secret']
        self.pin_code = section.get('pin_code')
        self.access_token = section.get('access_token')
        self.refresh_token = section.get('refresh_token')

        if not self.pin_code and not self.access_token and not self.refresh_token:
            raise RuntimeError('Please obtain a trakt PIN code and update the config.')

        self.custom_list = section.get('custom_list', self.custom_list) or None
        self.base_url = section.get('base_url', self.base_url)
        self.interval = float(section.get('interval', self.interval))
        self.timeout = float(section.get('timeout', 30))

    async def start(self):
        self.core.metadata.plugins.insert(0, TraktMetadataPlugin(self))
        self.core.download.post_processing_plugins.append(TraktPostProcessorPlugin(self))

    async def run(self):
        while True:
            await self._check_progress()
            await asyncio.sleep(self.interval)

    async def _retrying_request(self, method, url, headers, body):
        while True:
            async with self._trakt_sem:
                async with self.core.session.request(method, url, headers=headers, data=body,
                                                     timeout=self.timeout) as response:
                    if response.status == 401:
                        raise UnauthorizedError('%d %s' % (response.status, response.reason))
                    elif 200 <= response.status < 300:
                        return await response.read()

                    logger.error('Request {} {} failed: {} {}. Retrying in 15s.'.format(method, url, response.status,
                                                                                        response.reason))
                    await asyncio.sleep(15)

    async def _trakt_exchange_code(self, refresh_token=None):
        if not refresh_token:
            body = {
                'code': self.pin_code,
                'grant_type': 'authorization_code',
            }
        else:
            body = {
                'refresh_token': refresh_token,
                'grant_type': 'refresh_token',
            }

        body.update({
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'redirect_uri': 'urn:ietf:wg:oauth:2.0:oob',
        })

        response = await self._retrying_request(
            'POST',
            '%s/oauth/token' % self.base_url,
            {
                'Content-type': 'application/json',
                'trakt-api-key': self.client_id,
                'trakt-api-version': '2',
            },
            json.dumps(body)
        )

        data = json.loads(response)
        self.pin_code = ''
        self.access_token = str(data['access_token'])
        self.refresh_token = str(data['refresh_token'])
        self.core.config.set('slurp.backend.trakt', 'pin_code', self.pin_code)
        self.core.config.set('slurp.backend.trakt', 'access_token', self.access_token)
        self.core.config.set('slurp.backend.trakt', 'refresh_token', self.refresh_token)
        self.core.save_config()

    async def trakt_request(self, path_format, path_data=None, body=None):
        if not self.access_token:
            await self._trakt_exchange_code()

        headers = {
            'Content-type': 'application/json',
            'trakt-api-version': '2',
            'trakt-api-key': self.client_id,
            'Authorization': 'Bearer %s' % self.access_token
        }

        if body is None:
            method = 'GET'
            body = None
        else:
            method = 'POST'
            body = json.dumps(dict(
                body,
                username=self.username,
            ))

        url = '%s/%s' % (
            self.base_url,
            path_format.format(
                username=self.username,
                **(path_data or {})
            ),
        )

        while True:
            try:
                response = await self._retrying_request(method, url, headers, body)
            except UnauthorizedError:
                if not self.refresh_token:
                    self.access_token = ''
                    self.core.config.set('slurp.back_end.trakt', 'access_token', self.access_token)
                    self.core.save_config()
                    raise RuntimeError('Invalid refresh_token, please request a new PIN code and update settings.')

                refresh_token = self.refresh_token
                self.access_token = ''
                self.refresh_token = ''
                self.core.config.set('slurp.back_end.trakt', 'access_token', self.access_token)
                self.core.config.set('slurp.back_end.trakt', 'refresh_token', self.refresh_token)
                self.core.save_config()

                await self._trakt_exchange_code(refresh_token)
                headers['Authorization'] = 'Bearer %s' % self.access_token
            else:
                return json.loads(response)

    async def _add_or_remove_episode(self, show, season, episode, collected):
        item = BacklogItem(
            show['ids']['slug'],
            season,
            episode,
            {
                'ids': show['ids'],
                'show_title': show['title'],
            },
        )
        if collected:
            self.core.backlog.remove_episode(item)
        else:
            await self.core.backlog.add_episode(item)

    async def _process_show_progress(self, progress, show, rt_progress):
        coros = []
        for season in progress['seasons']:
            season_number = season['number']
            season_progress = rt_progress.get(season_number, [])
            for episode in season['episodes']:
                episode_number = episode['number']
                coros.append(self._add_or_remove_episode(
                    show,
                    season_number,
                    int(episode_number),
                    episode_number in season_progress,
                ))
        if coros:
            await asyncio.gather(*coros)

    async def _check_show_progress(self, progress, shows):
        async def check_progress(show):
            try:
                data = await self.trakt_request(
                    'shows/{slug}/progress/collection',
                    {
                        'slug': show['ids']['slug'],
                    },
                )
            except:
                logger.exception('Failed to get show progress for {}:'.format(show['title']))
            else:
                await self._process_show_progress(data, show, progress.get(show['ids']['slug'], {}))

        await asyncio.gather(*(check_progress(show) for show in shows))

    @staticmethod
    def _process_collection_progress(data):
        return {
            show['show']['ids']['slug']: {
                season['number']: [
                    episode['number']
                    for episode in season['episodes']
                ]
                for season in show['seasons']
            }
            for show in data
        }

    async def _process_list_content(self, data):
        shows = [show['show'] for show in data if show['type'] == 'show']

        removed_shows = self.core.backlog.shows - set([show['ids']['slug'] for show in shows])
        for show_id in removed_shows:
            self.core.backlog.remove_show(show_id)

        try:
            data = await self.trakt_request('sync/collection/shows')
        except:
            logger.exception('Failed to retrieve collection progress from trakt.tv:')
        else:
            await self._check_show_progress(self._process_collection_progress(data), shows)

    async def _check_progress(self):
        try:
            if self.custom_list:
                data = await self.trakt_request('users/{username}/lists/{list}/items', {'list': self.custom_list})
            else:
                data = await self.trakt_request('sync/watchlist/shows')
        except:
            logger.exception('Failed to get trakt.tv list:')
        else:
            await self._process_list_content(data)
