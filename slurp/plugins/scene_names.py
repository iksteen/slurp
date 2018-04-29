import asyncio

from slurp.plugin_types import MetadataPlugin

SCENE_NAMES = {
    248841: 'Scandal (US)',
    263365: 'Marvels Agents of S.H.I.E.L.D',
    281709: 'The Librarians (US)',
    321239: 'The Handmaids Tale',
}


class SceneNamesMetadataPlugin(MetadataPlugin):
    def __init__(self, core, *, loop=None):
        self.core = core
        self.loop = loop if loop is not None else asyncio.get_event_loop()

    async def start(self):
        # Ensure we come last, our truth is absolute.
        self.core.metadata.plugins.remove(self)
        self.core.metadata.plugins.append(self)

    async def run(self):
        pass

    async def enrich(self, episode_info):
        episode_info['metadata']['show_title'] = SCENE_NAMES.get(
            episode_info['ids']['tvdb'],
            episode_info['metadata']['show_title']
        )
