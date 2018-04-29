import asyncio

SCENE_NAMES = {
    78804: 'Doctor Who (2005)',
    110381: 'Archer (2009)',
    248841: 'Scandal (US)',
    262980: 'House of Cards (2013)',
    263365: 'Marvels Agents of S.H.I.E.L.D',
    265074: 'Legends (2014)',
    277169: 'Faking It (2014)',
    279121: 'The Flash (2014)',
    281535: 'Forever (2014)',
    281709: 'The Librarians (US)',
    321239: 'The Handmaids Tale',
}


class SceneNamesMetadataPlugin:
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
