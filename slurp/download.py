import asyncio
import logging
import os

from slurp.plugin_types import DownloadPlugin, PreProcessingPlugin, PostProcessingPlugin
from slurp.util import load_plugins, filter_show_name, guess_media_info

logger = logging.getLogger(__name__)


def guess_identity_for_path(path):
    filename = os.path.split(path)[1]

    info = guess_media_info(filename)
    if info.get('type') not in ('episode', 'movie') or \
            (info['type'] == 'episode' and ('season' not in info or 'episode' not in info)) or \
            (info['type'] == 'movie' and 'year' not in info):
        info = guess_media_info(path)
        if info.get('type') not in ('episode', 'movie') or \
                (info['type'] == 'episode' and ('season' not in info or 'episode' not in info)) or \
                (info['type'] == 'movie' and 'year' not in info):
            return []

    if info['type'] == 'episode':
        show = filter_show_name(info['title'])
        if 'year' in info:
            show += ' {}'.format(info['year'])
        if 'country' in info:
            show += ' {}'.format(str(info['country']).lower())

        season = info['season']
        if isinstance(info['episode'], int):
            episodes = frozenset([info['episode']])
        else:
            episodes = frozenset(info['episode'])

        return frozenset([
            (show, season, episode)
            for episode in episodes
        ])
    else:
        return frozenset([(filter_show_name(info['title']), info['year'])])


class Download:
    def __init__(self, core, *, loop=None):
        self.core = core
        self.loop = loop if loop is not None else asyncio.get_event_loop()

        self._blacklist = []

        self.pre_processing_plugins = load_plugins('pre_processing', PreProcessingPlugin, 10, core, loop=self.loop)
        self.post_processing_plugins = load_plugins('post_processing', PostProcessingPlugin, 10, core, loop=self.loop)
        self.download_plugins = load_plugins('download', DownloadPlugin, 10, core, loop=self.loop)

    async def start(self):
        plugins = self.pre_processing_plugins + self.post_processing_plugins + self.download_plugins
        return await asyncio.gather(*(plugin.start() for plugin in plugins))

    async def run(self):
        plugins = self.pre_processing_plugins + self.post_processing_plugins + self.download_plugins
        return await asyncio.gather(*(plugin.run() for plugin in plugins))

    @property
    def supported_media(self):
        return set().union(*(provider.media for provider in self.download_plugins))

    def is_downloading(self, backlog_item):
        return any(provider.is_downloading(backlog_item) for provider in self.download_plugins)

    async def download(self, backlog_items, data):
        backlog_items = [
            backlog_item
            for backlog_item in backlog_items
            if not self.is_downloading(backlog_item)
        ]
        if not backlog_items:
            return

        media = set(data['media'])

        for provider in self.download_plugins:
            if media & set(provider.media):
                break
        else:
            raise Exception('Could not find download provider for media types %s' % ','.join(media))

        await provider.download(backlog_items, data)

    async def download_completed(self, files):
        for processor in self.pre_processing_plugins:
            files = await processor.process(files)

        identity_backlog_item_key_map = {
            backlog_item.identity(): backlog_item.key
            for backlog_item in self.core.backlog.values()
        }

        def find_backlog_keys(path):
            episode_keys = guess_identity_for_path(path)
            return frozenset([
                identity_backlog_item_key_map[episode_key]
                for episode_key in episode_keys
                if episode_key in identity_backlog_item_key_map
            ])

        files = {
            path: {
                'size': file_size,
                'backlog_keys': find_backlog_keys(path),
            }
            for path, file_size in files
        }

        backlog_items = [
            self.core.backlog[backlog_item_key]
            for backlog_item_key in set().union(*[v['backlog_keys'] for v in files.values()])
        ]

        await asyncio.gather(*(processor.process(backlog_items, files) for processor in self.post_processing_plugins))

        for backlog_item in backlog_items:
            logger.info('Download completed: {}'.format(backlog_item))
            self.core.backlog.remove_item(backlog_item)
