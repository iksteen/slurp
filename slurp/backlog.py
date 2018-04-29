import asyncio

import logging

from slurp.util import format_episode_info, key_for_episode

logger = logging.getLogger(__name__)


class Backlog:
    def __init__(self, core):
        self.core = core
        self._backlog = {}
        self._notify_backlog = []

    def register_notify_backlog(self, callback):
        self._notify_backlog.append(callback)
        for backlog_item in self._backlog:
            callback(*backlog_item)

    async def add_episode(self, episode_info):
        logger.info('Adding {} to backlog queue'.format(format_episode_info(episode_info)))
        key = key_for_episode(episode_info)
        if key in self._backlog:
            return

        await self.core.metadata.enrich(episode_info)

        self._backlog[key] = episode_info

        await asyncio.gather(*(callback(episode_info) for callback in self._notify_backlog))

    def remove_episode(self, episode_info):
        if self._backlog.pop(key_for_episode(episode_info), None) is not None:
            logger.info('Removed {} from backlog queue'.format(format_episode_info(episode_info)))

    @property
    def shows(self):
        return set(key[0] for key in self._backlog.keys())

    def remove_show(self, show):
        episode_keys = [key for key in self._backlog.keys() if key[0] == show]
        for episode_key in episode_keys:
            self._backlog.pop(episode_key)
            logger.info('Removed {} S{:02}E{:02} from backlog queue'.format(*episode_key))

    def __nonzero__(self):
        return bool(self._backlog)

    def __contains__(self, item):
        return item in self._backlog

    def __iter__(self):
        return self._backlog.__iter__()

    def values(self):
        return self._backlog.values()

    def items(self):
        return self._backlog.items()

    def __getitem__(self, item):
        return self._backlog[item]

    def get(self, item, default=None):
        return self._backlog.get(item, default)
