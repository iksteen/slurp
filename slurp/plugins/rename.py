import asyncio
import logging
import mimetypes
from configparser import NoSectionError

import os
import re
import shutil

from slurp.backlog import EpisodeBacklogItem, MovieBacklogItem
from slurp.plugin_types import PostProcessingPlugin

logger = logging.getLogger(__name__)

UNSAFE_CHARS = re.compile(r'[\\/:*?"<>|]')

COMMON_EXTENSIONS = {
    'video/x-matroska': '.mkv',
}


class RenameProcessingPlugin(PostProcessingPlugin):
    _episode_destination = None
    _episode_format = os.path.join(
        '{show}',
        'Season {season}',
        '{show} - {season_str}{episode_str} - {title}{ext}'
    )
    _movie_destination = None
    _movie_format = '{title} ({year}){ext}'

    _strategy = 'copy'
    _dir_mode = 0o755
    _file_mode = 0o644

    def __init__(self, core, *, loop=None):
        self.core = core
        self.loop = loop if loop is not None else asyncio.get_event_loop()

        try:
            section = dict(core.config.items('slurp.processing.renamer'))
        except NoSectionError:
            section = {}

        self._episode_destination = section.get('episode_destination')
        if not self._episode_destination:
            raise ValueError('You must set an episode destination path to use the renamer plugin.')
        self._episode_format = section.get('format', self._episode_format)

        self._movie_destination = section.get('movie_destination')
        if not self._episode_destination:
            raise ValueError('You must set a movie destination path to use the renamer plugin.')
        self._movie_format = section.get('format', self._movie_format)

        self._strategy = section.get('strategy', self._strategy)
        self._dir_mode = int(section.get('dir_mode', oct(self._dir_mode)), 8)
        self._file_mode = int(section.get('file_mode', oct(self._file_mode)), 8)
        if self._strategy not in ('copy', 'move', 'symlink'):
            raise ValueError('Invalid rename plugin strategy')

    async def start(self):
        pass

    async def run(self):
        pass

    async def process(self, _, files):
        backlog_keys = self.core.backlog.keys()
        rename_files = {}

        for path, path_info in files.items():
            file_size = path_info['size']
            file_backlog_keys = path_info['backlog_keys']

            if not file_backlog_keys:
                logger.info('Ignoring file {}, not enough information.'.format(path))
                continue

            if not file_backlog_keys & backlog_keys:
                logger.info('Ignoring file {}, no backlog found'.format(path))
                continue

            mime, _ = mimetypes.guess_type(path)
            if mime is None or not mime.startswith('video/'):
                logger.info('Ignoring file {}, no video mimetype'.format(path))
                continue

            ext = COMMON_EXTENSIONS.get(mime, mimetypes.guess_extension(mime))

            key = (ext, file_backlog_keys)
            if file_size > rename_files.get(key, (None, 0))[1]:
                rename_files[key] = (path, file_size)

        files = [
            (path, ext, [
                self.core.backlog[backlog_key]
                for backlog_key in file_backlog_keys
            ])
            for (ext, file_backlog_keys), (path, _) in rename_files.items()
        ]
        return await self._rename_files(files)

    async def _rename_files(self, files):
        def get_episode_destination(backlog_items, ext):
            backlog_items = sorted(backlog_items, key=lambda item: item.episode)

            show = UNSAFE_CHARS.sub('_', backlog_items[0].metadata['show_title'])

            season = backlog_items[0].season
            season_str = 'S%02d' % season

            episodes = [e.episode for e in backlog_items]
            episode = episodes[0]

            if len(episodes) > 1:
                episode_str = 'E%02d-E%02d' % (min(*episodes), max(*episodes))
            else:
                episode_str = 'E%02d' % episodes[0]

            title = UNSAFE_CHARS.sub(' ', '&'.join([e.metadata['episode_title'] for e in backlog_items]))

            return os.path.join(
                self._episode_destination,
                self._episode_format.format(
                    show=show,
                    season=season,
                    season_str=season_str,
                    episode=episode,
                    episode_str=episode_str,
                    title=title,
                    ext=ext,
                )
            )

        def get_movie_destination(backlog_item, ext):
            title = UNSAFE_CHARS.sub('_', backlog_item.metadata['movie_title'])
            year = backlog_item.metadata['year']

            return os.path.join(
                self._movie_destination,
                self._movie_format.format(
                    title=title,
                    year=year,
                    ext=ext,
                )
            )

        def get_destination(backlog_items, ext):
            if isinstance(backlog_items[0], EpisodeBacklogItem):
                return get_episode_destination(backlog_items, ext)
            elif isinstance(backlog_items[0], MovieBacklogItem):
                return get_movie_destination(backlog_items[0], ext)
            else:
                return None

        return await self.loop.run_in_executor(
            None,
            self._copy_or_move_files,
            [
                (
                    path,
                    get_destination(backlog_items, ext)
                )
                for path, ext, backlog_items in files
            ]
        )

    def _copy_or_move_files(self, rename_files):
        for source, destination in rename_files:
            if destination is None:
                continue
            try:
                self._copy_or_move_file(source, destination)
            except Exception as e:
                def log_error(e):
                    def log():
                        logger.exception(
                            'Failed to %s %s to %s' % (self._strategy, source, destination),
                            exc_info=e
                        )
                    return log
                self.loop.call_soon_threadsafe(log_error(e))

    def _copy_or_move_file(self, source, destination):
        mask = os.umask(0)
        try:
            destination_dir = os.path.split(destination)[0]
            if not os.path.isdir(destination_dir):
                os.makedirs(destination_dir, self._dir_mode)

            if self._strategy == 'symlink':
                os.symlink(source, destination)
                log_message = 'Linked %s to %s' % (source, destination)
            elif self._strategy == 'copy':
                shutil.copyfile(source, destination + '.tmp')
                os.rename(destination + '.tmp', destination)
                os.chmod(destination, self._file_mode)
                log_message = 'Copied %s to %s' % (source, destination)
            else:
                shutil.move(source, destination)
                os.chmod(destination, self._file_mode)
                log_message = 'Moved %s to %s' % (source, destination)

            self.loop.call_soon_threadsafe(
                logger.info,
                log_message,
            )
        finally:
            os.umask(mask)
