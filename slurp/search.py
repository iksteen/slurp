import asyncio
import itertools
import logging
from cidict import cidict
from configparser import NoSectionError

from slurp.plugin_types import SearchPlugin
from slurp.util import filter_show_name, guess_episode_info, parse_option_list, load_plugins, format_episode_info

DEFAULT_BLACKLIST = 'core2hd,chamee'

logger = logging.getLogger(__name__)


class Search:
    _search_interval = 3600
    _start_delay = 300
    _sort_order = ('verified', 'origin', 'rank')

    def __init__(self, core, *, loop=None):
        self.core = core
        self.loop = loop if loop is not None else asyncio.get_event_loop()

        self.plugins = []

        self._dl_blacklist = {}

        self._filter = {}
        self._require = {}

        blacklist = DEFAULT_BLACKLIST
        try:
            section = dict(core.config.items('slurp.search'))
            blacklist = section.get('blacklist', blacklist)
            self._search_interval = int(section.get('interval', self._search_interval))
            self._start_delay = int(section.get('start_delay', self._start_delay))
            self._sort_order = parse_option_list(section.get('sort_order', ','.join(self._sort_order)))

            for key, value in section.items():
                if key.startswith('filter.'):
                    filter_key = key.split('.', 1)[1]
                    self._filter[filter_key] = parse_option_list(value)
                elif key.startswith('require.'):
                    require_key = key.split('.', 1)[1]
                    self._require[require_key] = parse_option_list(value)
        except NoSectionError:
            pass
        except:
            logger.exception('Invalid search configuration:')

        self._blacklist = parse_option_list(blacklist)

        self.plugins = load_plugins('search', SearchPlugin, 0, core, loop=self.loop)

    async def start(self):
        self.core.backlog.register_notify_backlog(self._search_episode)
        await asyncio.gather(*(plugin.start() for plugin in self.plugins))

    async def run(self):
        async def loop():
            await asyncio.sleep(self._start_delay)
            while True:
                await self._search_backlog()
                await asyncio.sleep(self._search_interval)

        await asyncio.gather(loop(), *(plugin.run() for plugin in self.plugins))

    async def _search_backlog(self):
        if not self.core.backlog:
            logger.info('Not searching backlog, no backlog found')
            return

        await asyncio.gather(*(
            self._search_episode(episode_info)
            for episode_info in self.core.backlog.values()
        ))

    async def _search_episode(self, episode_info):
        async def search(plugin):
            try:
                return await plugin.search(episode_info)
            except:
                logger.exception('Error while searching {} using {}:'.format(episode_info, plugin))
                return []

        if self.core.download.is_downloading(episode_info):
            return

        logger.info('Searching for {}'.format(format_episode_info(episode_info)))

        results = await asyncio.gather(*(search(plugin) for plugin in self.plugins))
        results = tuple(itertools.chain.from_iterable(results))
        if not results:
            return
        results = tuple(self._filter_by_medium(results, self.core.download.supported_media))
        results = tuple(self._filter_blacklist(results))
        results = tuple(self._filter_dl_blacklist(results))
        results = tuple(self._guess_episode_info(results))
        results = tuple(self._filter_by_info(results, episode_info))
        results = tuple(self._sort_search_results(results))
        await self._download_result(results, episode_info)

    def _filter_by_medium(self, results, supported_media):
        return filter(lambda result: set(result['media']) & supported_media, results)

    def _filter_blacklist(self, results):
        return filter(
            lambda result: not any([
                phrase in result['title'].lower()
                for phrase in self._blacklist
            ]),
            results
        )

    def _filter_dl_blacklist(self, results):
        return filter(
            lambda result: not any([
                data == dl
                for medium, data in result['media'].items()
                for dl in self._dl_blacklist.get(medium, [])
            ]),
            results
        )

    def _guess_episode_info(self, results):
        return [
            (
                result,
                cidict(guess_episode_info(result['title'])),
            )
            for result in results
        ]

    def _filter_by_info(self, results, episode_info):
        def set_from_value_or_list(value):
            if not isinstance(value, list):
                value = [value]
            return set([str(v).lower() for v in value])

        show_info = guess_episode_info(episode_info['metadata']['show_title'])
        show_title = filter_show_name(show_info['title'])
        season = episode_info['season']
        episode = episode_info['episode']

        return [
            (result, info)
            for result, info in results
            if
            (
                    'title' in info and filter_show_name(info['title']) == show_title
                    and ('year' not in show_info or show_info['year'] == info.get('year'))
                    and ('country' not in show_info or show_info['country'] == info.get('country'))
                    and 'season' in info and info['season'] == season
                    and 'episode' in info and episode in info['episode']
                    and
                    (
                        not any([
                            (value & set_from_value_or_list(info.get(key, 'unknown')))
                            for key, value in self._filter.items()
                        ])
                    )
                    and
                    (
                        all([
                            (value & set_from_value_or_list(info.get(key, 'unknown')))
                            for key, value in self._require.items()
                        ])
                    )
            )
        ]

    def _sort_search_results(self, results):
        def sort_key_item(result, info, key):
            if key == 'verified':
                return result['verified'] and 1 or 0
            elif key == 'origin':
                return -self.plugins.index(result['origin'])
            elif key == 'rank':
                return result['rank']
            elif key == 'proper':
                return info.get('proper_count', 0)
            else:
                logger.warning('Invalid sort key %s' % key)
                return 0

        def sort_key(result_info):
            result, info = result_info
            return tuple(
                -sort_key_item(result, info, key)
                for key in self._sort_order
            )

        return sorted(
            results,
            key=sort_key,
        )

    async def _download_result(self, results, episode_info):
        if not results:
            return

        result, info = results[0]
        season = episode_info['season']

        for medium, data in result['media'].items():
            self._dl_blacklist.setdefault(
                medium,
                []
            ).append(data)

        episode_list = info['episode']

        episodes_info = []
        for episode in episode_list:
            key = (episode_info['show_id'], season, episode)
            episode_info = self.core.backlog.get(key)
            if episode_info is not None:
                episodes_info.append(episode_info)

        return await self.core.download.download(episodes_info, result)
