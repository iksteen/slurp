import asyncio
import logging
import os
from configparser import NoSectionError

import pkg_resources
from slurp.backlog import Backlog
from slurp.download import Download
from slurp.metadata import Metadata
from slurp.search import Search

logger = logging.getLogger(__name__)


class Core:
    def __init__(self, config_path, config, *, session, loop=None):
        self.config_path = config_path
        self.config = config
        self.session = session
        self.loop = loop if loop is not None else asyncio.get_event_loop()

        self.backlog = Backlog(self)
        self.metadata = Metadata(self, loop=self.loop)
        self.search = Search(self, loop=self.loop)
        self.download = Download(self, loop=self.loop)

        try:
            section = dict(config.items('slurp'))
            backend_name = section.get('backend', 'trakt')
        except NoSectionError:
            backend_name = 'trakt'

        for entrypoint in pkg_resources.iter_entry_points('slurp.plugins.backend'):
            if entrypoint.name == backend_name:
                backend_plugin = entrypoint.load()
                self.backend = backend_plugin(self, loop=self.loop)
                break
        else:
            logger.error('Could not find back end plugin %s' % backend_name)
            self.backend = None

    async def run(self):
        await asyncio.gather(
            self.metadata.start(),
            self.search.start(),
            self.download.start(),
            self.backend.start(),
        )
        return await asyncio.gather(
            self.metadata.run(),
            self.search.run(),
            self.download.run(),
            self.backend.run(),
        )

    def save_config(self):
        with open(self.config_path + '.tmp', 'w') as f:
            self.config.write(f)
        os.rename(self.config_path + '.tmp', self.config_path)
