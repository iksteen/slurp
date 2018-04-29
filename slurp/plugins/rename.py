import asyncio
import logging
import mimetypes
from configparser import NoSectionError

import os
import re
import shutil

logger = logging.getLogger(__name__)

UNSAFE_CHARS = re.compile(r'[\\/:*?"<>|]')

COMMON_EXTENSIONS = {
    'video/x-matroska': '.mkv',
}


class RenameProcessingPlugin:
    _destination = None
    _filename_format = os.path.join(
        '{show}',
        'Season {season}',
        '{show} - {season_str}{episode_str} - {title}{ext}'
    )
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

        self._destination = section.get('destination')
        if not self._destination:
            raise ValueError('You must set a destination path to use the renamer plugin.')

        self._filename_format = section.get('format', self._filename_format)
        self._strategy = section.get('strategy', self._strategy)
        self._dir_mode = int(section.get('dir_mode', oct(self._dir_mode)), 8)
        self._file_mode = int(section.get('file_mode', oct(self._file_mode)), 8)
        if self._strategy not in ('copy', 'move', 'symlink'):
            raise ValueError('Invalid rename plugin strategy')

    async def start(self):
        self.core.download.register_notify_completed(self._on_download_completed)

    async def run(self):
        pass

    async def __call__(self, files):
        return files

    async def _on_download_completed(self, _, files):
        backlog_keys = set(self.core.backlog)
        rename_files = {}

        for path, path_info in files.items():
            file_size = path_info['size']
            file_keys = path_info['episode_keys']
            print(file_keys)

            if not file_keys:
                logger.info('Ignoring file {}, not enough information.'.format(path))
                continue

            if not file_keys & backlog_keys:
                logger.info('Ignoring file {}, no backlog found'.format(path))
                continue

            mime, _ = mimetypes.guess_type(path)
            if mime is None or not mime.startswith('video/'):
                logger.info('Ignoring file {}, no video mimetype'.format(path))
                continue

            ext = COMMON_EXTENSIONS.get(mime, mimetypes.guess_extension(mime))

            key = (ext, file_keys)
            if file_size > rename_files.get(key, (None, 0))[1]:
                rename_files[key] = (path, file_size)

        files = [
            (path, ext, [
                self.core.backlog.get(file_key, {
                    'show': file_key[0],
                    'season': file_key[1],
                    'episode': file_key[2],
                    'title': 'UNKNOWN',
                })
                for file_key in file_keys
            ])
            for (ext, file_keys), (path, _) in rename_files.items()
        ]
        return await self._rename_files(files)

    async def _rename_files(self, files):
        def get_destination(episodes_info, ext):
            episodes_info = sorted(episodes_info, key=lambda e: e['episode'])

            show = UNSAFE_CHARS.sub('_', episodes_info[0]['metadata']['show_title'])

            season = episodes_info[0]['season']
            season_str = 'S%02d' % season

            episodes = [e['episode'] for e in episodes_info]
            episode = episodes[0]

            if len(episodes_info) > 1:
                episode_str = 'E%02d-E%02d' % (min(*episodes), max(*episodes))
            else:
                episode_str = 'E%02d' % episodes[0]

            title = UNSAFE_CHARS.sub(' ', '&'.join([e['metadata']['episode_title'] for e in episodes_info]))

            return os.path.join(
                self._destination,
                self._filename_format.format(
                    show=show,
                    season=season,
                    season_str=season_str,
                    episode=episode,
                    episode_str=episode_str,
                    title=title,
                    ext=ext,
                )
            )

        return await self.loop.run_in_executor(
            None,
            self._copy_or_move_files,
            [
                (
                    path,
                    get_destination(episodes_info, ext)
                )
                for path, ext, episodes_info in files
            ]
        )

    def _copy_or_move_files(self, rename_files):
        for source, destination in rename_files:
            try:
                self._copy_or_move_file(source, destination)
            except Exception as e:
                def log_error():
                    logger.exception(
                        'Failed to %s %s to %s' % (self._strategy, source, destination),
                        exc_info=e
                    )
                self.loop.call_soon_threadsafe(log_error)

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
