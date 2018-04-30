import logging

logger = logging.getLogger(__name__)


class BacklogItem:
    def __init__(self, show_id, season, episode, metadata):
        self.key = object()
        self.show_id = show_id
        self.season = season
        self.episode = episode
        self.metadata = metadata

    def __eq__(self, other):
        return self.show_id == other.show_id and self.season == other.season and self.episode == other.episode

    def __str__(self):
        return '{show_title} S{season:02d}E{episode:02d}'.format(
            show_title=self.metadata['show_title'],
            season=self.season,
            episode=self.episode,
        )


class Backlog:
    def __init__(self, core):
        self.core = core
        self._backlog = {}

    async def add_episode(self, item):
        if self.find(item) is not None:
            return
        logger.info('Adding {} to backlog queue'.format(item))

        await self.core.metadata.enrich(item)

        self._backlog[item.key] = item

        await self.core.search.search_backlog_item(item)

    def remove_episode(self, item):
        item = self.find(item)
        if item is not None:
            del self._backlog[item.key]
            logger.info('Removed {} from backlog queue'.format(item))

    @property
    def shows(self):
        return set(item.show_id for item in self._backlog.values())

    def remove_show(self, show_id):
        episode_items = [item for item in self._backlog.values() if item.show_id == show_id]
        for item in episode_items:
            del self._backlog[item.key]
            logger.info('Removed {} from backlog queue'.format(item))

    def empty(self):
        return not bool(self._backlog)

    def keys(self):
        return set(self._backlog.keys())

    def values(self):
        return self._backlog.values()

    def __getitem__(self, item):
        return self._backlog[item]

    def find(self, placeholder):
        for item in self._backlog.values():
            if item == placeholder:
                return item
        else:
            return None
