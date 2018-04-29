import asyncio
import os
import logging
import re
import itertools

import rarfile

from slurp.plugin_types import ProcessingPlugin

logger = logging.getLogger(__name__)

DETECT_PART = re.compile(r'\.part(\d+)\.rar')


def extract_archive(path):
    archive_dir, archive_filename = os.path.split(path)
    extract_dir = os.path.join(
        archive_dir,
        '__extracted__',
        os.path.splitext(archive_filename)[0],
    )
    if not os.path.isdir(extract_dir):
        os.makedirs(extract_dir)

    rf = rarfile.RarFile(path)
    rf.extractall(extract_dir)

    extracted_files = []
    for f in rf.infolist():
        if f.isdir():
            continue

        native_filename = f.filename.replace('\\', '/')

        extracted_files.append((
            os.path.join(extract_dir, native_filename),
            f.file_size
        ))

    return extracted_files


class UnrarProcessingPlugin(ProcessingPlugin):
    def __init__(self, core, *, loop=None):
        self.core = core
        self.loop = loop if loop is not None else asyncio.get_event_loop()
        self.sem = asyncio.Semaphore(2, loop=self.loop)

    async def start(self):
        pass

    async def run(self):
        pass

    async def process(self, files):
        async with self.sem:
            async def process_archive(path):
                try:
                    return await self.loop.run_in_executor(None, extract_archive, path)
                except:
                    logger.exception('Failed to extract RAR archive {}:'.format(path))
                    return []

            fs = []
            for path, size in files:
                filename = os.path.split(path)[1]
                if os.path.splitext(filename)[1] == '.rar':
                    m = DETECT_PART.search(path)
                    if m and int(m.group(1)) != 1:
                        # Only extract the first part of a multi-part rar file.
                        continue
                    logger.info('Extracting RAR archive: {}'.format(path))
                    fs.append(process_archive(path))

            if not fs:
                return files

            try:
                extra_files = await asyncio.gather(*fs, loop=self.loop)
                return tuple(itertools.chain.from_iterable([files] + extra_files))
            except:
                logger.exception('Failed concatenate file list:')
                return files
