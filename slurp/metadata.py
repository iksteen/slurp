import asyncio
import logging

from slurp.plugin_types import MetadataPlugin
from slurp.util import load_plugins

logger = logging.getLogger(__name__)


class Metadata:
    def __init__(self, core, *, loop=None):
        self.core = core
        self.loop = loop if loop is not None else asyncio.get_event_loop()
        self.plugins = load_plugins('metadata', MetadataPlugin, 10, core, loop=self.loop)

    async def start(self):
        return await asyncio.gather(*(plugin.start() for plugin in self.plugins), loop=self.loop)

    async def run(self):
        return await asyncio.gather(*(plugin.run() for plugin in self.plugins), loop=self.loop)

    async def enrich(self, backlog_item):
        for plugin in self.plugins:
            await plugin.enrich(backlog_item)
