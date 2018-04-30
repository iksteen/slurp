import logging

from slurp.util import filter_show_name

logger = logging.getLogger(__name__)


class BacklogItem:
    def __init__(self, object_id, metadata):
        self.key = object()
        self.object_id = object_id
        self.metadata = metadata

    def identity(self):
        raise NotImplemented


class EpisodeBacklogItem:
    def __init__(self, object_id, season, episode, metadata):
        self.key = object()
        self.object_id = object_id
        self.season = season
        self.episode = episode
        self.metadata = metadata

    def identity(self):
        return (
            filter_show_name(self.metadata['show_title']),
            self.season,
            self.episode,
        )

    def __eq__(self, other):
        return isinstance(other, EpisodeBacklogItem) and self.object_id == other.object_id and \
               self.season == other.season and self.episode == other.episode

    def __str__(self):
        return '{show_title} S{season:02d}E{episode:02d}'.format(
            season=self.season,
            episode=self.episode,
            **self.metadata,
        )


class MovieBacklogItem(BacklogItem):
    def __init__(self, object_id, metadata):
        super().__init__(object_id, metadata)

    def identity(self):
        return (
            filter_show_name(self.metadata['movie_title']),
            self.metadata['year'],
        )

    def __eq__(self, other):
        return isinstance(other, MovieBacklogItem) and self.object_id == other.object_id

    def __str__(self):
        return '{movie_title} ({year})'.format(**self.metadata)


class Backlog:
    def __init__(self, core):
        self.core = core
        self._backlog = {}

    async def add_item(self, item):
        if self.find(item) is not None:
            return
        logger.info('Adding {} to backlog queue'.format(item))

        await self.core.metadata.enrich(item)

        self._backlog[item.key] = item

        await self.core.search.search_backlog_item(item)

    def remove_item(self, item):
        item = self.find(item)
        if item is not None:
            del self._backlog[item.key]
            logger.info('Removed {} from backlog queue'.format(item))

    def object_ids(self, restrict_type=None):
        return set(
            item.object_id
            for item in self._backlog.values()
            if restrict_type is None or isinstance(type, restrict_type)
        )

    def remove_by_object_id(self, object_id):
        items = [item for item in self._backlog.values() if item.object_id == object_id]
        for item in items:
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
