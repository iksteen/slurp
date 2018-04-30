import asyncio
import logging

from slurp.plugin_types import MetadataPlugin

logger = logging.getLogger(__name__)


class TheTVDBMetadataPlugin(MetadataPlugin):
    def __init__(self, core, *, loop=None):
        self.core = core
        self.loop = loop if loop is not None else asyncio.get_event_loop()

        self._token = None

        section = dict(core.config.items('slurp.metadata.tvdb'))
        self._api_key = section['api_key']

    async def start(self):
        pass

    async def run(self):
        pass

    async def enrich(self, backlog_item):
        retries = 2
        try:
            while retries > 0:
                retries -= 1
                headers = {
                    'Accept': 'application/json',
                }

                if self._token is None:
                    url = 'https://api.thetvdb.com/login'
                    data = {'apikey': self._api_key}
                    async with self.core.session.post(url, headers=headers, json=data) as response:
                        response.raise_for_status()
                        data = await response.json()
                    self._token = data['token']

                headers['Authorization'] = 'Bearer {}'.format(self._token)

                url = 'https://api.thetvdb.com/series/{}'.format(backlog_item.metadata['ids']['tvdb'])
                async with self.core.session.get(url, headers=headers) as response:
                    if response.status == 401:
                        self._token = None
                        continue
                    response.raise_for_status()
                    data = await response.json()
                backlog_item.metadata['show_title'] = data['data']['seriesName']
                return
            else:
                raise Exception('Authentication keeps failing.')
        except:
            logger.exception('Failed to query TheTVDB:')
