import asyncio
import logging

from slurp.plugin_types import ProcessingPlugin, DownloadPlugin
from slurp.util import format_episode_info, guess_episode_keys_for_path, load_plugins, filter_show_name

logger = logging.getLogger(__name__)


async def log_completed(episodes_info, _):
    for episode_info in episodes_info:
        logger.info('Download completed: {}'.format(format_episode_info(episode_info)))


class Download:
    def __init__(self, core, *, loop=None):
        self.core = core
        self.loop = loop if loop is not None else asyncio.get_event_loop()

        self._blacklist = []

        self._notify_completed = [log_completed]

        self.processing_plugins = load_plugins('processing', ProcessingPlugin, 10, core, loop=self.loop)
        self.download_plugins = load_plugins('download', DownloadPlugin, 10, core, loop=self.loop)

    async def start(self):
        return await asyncio.gather(*(plugin.start() for plugin in self.processing_plugins + self.download_plugins))

    async def run(self):
        return await asyncio.gather(*(plugin.run() for plugin in self.processing_plugins + self.download_plugins))

    @property
    def supported_media(self):
        return set().union(*(provider.media for provider in self.download_plugins))

    def is_downloading(self, episode_info):
        return any(provider.is_downloading(episode_info) for provider in self.download_plugins)

    async def download(self, episodes_info, data):
        episodes_info = [
            episode_info
            for episode_info in episodes_info
            if not self.is_downloading(episode_info)
        ]
        if not episodes_info:
            return

        media = set(data['media'])

        for provider in self.download_plugins:
            if media & set(provider.media):
                break
        else:
            raise Exception('Could not find download provider for media types %s' % ','.join(media))

        await provider.download(episodes_info, data)

    def register_notify_completed(self, callback):
        self._notify_completed.append(callback)

    async def download_completed(self, files):
        for post_processor in self.processing_plugins:
            files = await post_processor.process(files)

        backlog_map = {
            (
                filter_show_name(episode_info['metadata']['show_title']),
                episode_info['season'],
                episode_info['episode'],
            ): episode_key
            for episode_key, episode_info in self.core.backlog.items()
        }

        def find_episode_keys(path):
            episode_keys = guess_episode_keys_for_path(path)
            return frozenset([
                backlog_map[episode_key]
                for episode_key in episode_keys
                if episode_key in backlog_map
            ])

        files = {
            path: {
                'size': file_size,
                'episode_keys': find_episode_keys(path),
            }
            for path, file_size in files
        }

        episodes_info = [
            self.core.backlog[episode_key]
            for episode_key in set().union(
                *[v['episode_keys'] for v in files.values()]
            )
        ]

        await asyncio.gather(*(callback(episodes_info, files) for callback in self._notify_completed))

        for episode_info in episodes_info:
            self.core.backlog.remove_episode(episode_info)
