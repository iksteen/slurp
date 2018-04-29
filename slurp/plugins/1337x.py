import asyncio
import logging
import urllib.parse

import re
from bs4 import BeautifulSoup

from slurp.plugin_types import SearchPlugin
from slurp.util import format_episode_info

logger = logging.getLogger(__name__)


class LeetXSearchPlugin(SearchPlugin):
    def __init__(self, core, *, loop=None):
        self.core = core
        self.loop = loop if loop is not None else asyncio.get_event_loop()
        self.sem = asyncio.Semaphore(4, loop=self.loop)

    async def start(self):
        pass

    async def run(self):
        pass

    async def search(self, episode_info):
        async def get_info(item):
            link = item.find('td', class_='name').find('a', href=re.compile('^/torrent/'))
            details_url = urllib.parse.urljoin(search_url, link['href'])
            async with self.sem, self.core.session.get(details_url) as response:
                response_text = await response.text()

            magnet_uri = BeautifulSoup(response_text, 'lxml').find('a', href=re.compile('^magnet:'))['href']
            return {
                'origin': self,
                'title': str(link.string),
                'verified': False,
                'rank': int(item.find('td', class_='seeds').string),
                'media': {
                    'torrent:magnet': {
                        'magnetURI': magnet_uri,
                    },
                },
            }

        query = format_episode_info(episode_info)
        search_url = 'http://1337x.to/search/{}/1/'.format(urllib.parse.quote_plus(query))
        async with self.sem, self.core.session.get(search_url) as response:
            response_text = await response.text()

        body = BeautifulSoup(response_text, 'lxml').tbody
        if body is None:
            return []

        return await asyncio.gather(*(
            get_info(item)
            for item in body('tr')
        ))
