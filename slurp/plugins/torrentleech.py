import asyncio
import json
import logging

import asyncpg
import datetime
import dateutil
import guessit
from babelfish import Language, Country
from defusedxml.ElementTree import fromstring

from slurp.backlog import EpisodeBacklogItem, MovieBacklogItem
from slurp.plugin_types import SearchPlugin
from slurp.util import filter_show_name

logger = logging.getLogger(__name__)


def json_serializer(obj):
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    elif isinstance(obj, Language):
        return str(obj)
    elif isinstance(obj, Country):
        return str(obj)
    raise TypeError("Type %s not serializable" % type(obj))


def json_dumps(value):
    return json.dumps(value, default=json_serializer)


class TorrentLeechSearchPlugin(SearchPlugin):
    def __init__(self, core, *, loop=None):
        self.core = core
        self.loop = loop if loop is not None else asyncio.get_event_loop()
        self._pool = None

        section = dict(core.config.items('slurp.search.torrentleech'))
        self._rss_url = 'https://rss.torrentleech.org/{}'.format(section['rss_key'])
        self._db_host = section.get('db_host', None)
        self._db_port = section.get('db_port', None)
        self._db_user = section.get('db_user', None)
        self._db_password = section.get('db_password', None)
        self._db_name = section.get('db_name', 'slurp')

    async def start(self):
        async def init(conn):
            await conn.set_type_codec(
                'jsonb',
                schema='pg_catalog',
                encoder=json_dumps,
                decoder=json.loads,
            )
        self._pool = await asyncpg.create_pool(
            host=self._db_host,
            port=self._db_port,
            user=self._db_user,
            password=self._db_password,
            database=self._db_name,
            init=init,
        )
        await self._pool.execute('''
            CREATE TABLE IF NOT EXISTS torrentleech (
                guid text NOT NULL PRIMARY KEY,
                title text NOT NULL,
                pubdate timestamp without time zone NOT NULL,
                comments text NOT NULL,
                link text NOT NULL,
                description text NOT NULL,
                category text NOT NULL,
                seeders integer,
                leechers integer,
                metadata jsonb NOT NULL
            )
        ''')

    async def run(self):
        while True:
            try:
                async with await self.core.session.get(self._rss_url) as resp:
                    data = await resp.text()
            except:
                logger.exception('Failed to retrieve torrentleech rss:')
                await asyncio.sleep(5)
                continue

            try:
                root = fromstring(data)
            except:
                logger.exception('Failed to parse torrentleech rss:')
                await asyncio.sleep(5)
                continue

            channel = root.find('channel')
            for item in reversed(channel.findall('item')):
                title = item.find('title').text
                pub_date = dateutil.parser.parse(item.find('pubDate').text, ignoretz=True)
                guid = item.find('guid').text
                comments = item.find('comments').text
                link = item.find('link').text
                description = item.find('description').text
                metadata = {
                    key: value
                    for key, value in (
                        item.split(': ', 1)
                        for item in description.split(' - ')
                    )
                }

                category = metadata.get('Category')

                if 'Seeders' in metadata:
                    seeders = int(metadata['Seeders'])
                else:
                    seeders = None

                if 'Leechers' in metadata:
                    leechers = int(metadata['Leechers'])
                else:
                    leechers = None

                try:
                    metadata = dict(guessit.guessit(link.rsplit('/', 1)[-1]).items())
                except Exception:
                    logger.exception('Failed to parse TL data:')
                    continue

                async with self._pool.acquire() as conn:
                    txn = conn.transaction()
                    await txn.start()
                    try:
                        await self._pool.execute(
                            '''
                                INSERT INTO torrentleech (title, pubdate, guid, comments, link, description, category,
                                                          seeders, leechers, metadata)
                                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb)
                                ON CONFLICT (guid) DO UPDATE SET seeders = EXCLUDED.seeders, leechers = EXCLUDED.leechers
                            ''',
                            title,
                            pub_date,
                            guid,
                            comments,
                            link,
                            description,
                            category,
                            seeders,
                            leechers,
                            metadata,
                        )
                    except:
                        logger.exception('Failed to execute query:')
                        await txn.rollback()
                    else:
                        await txn.commit()

            ttl = 60 * int(channel.find('ttl').text)
            await asyncio.sleep(ttl)

    async def search(self, backlog_item):
        if isinstance(backlog_item, EpisodeBacklogItem):
            results = await self._pool.fetch(
                '''
                    SELECT *
                    FROM torrentleech
                    WHERE metadata->>'type' = 'episode'
                    AND metadata->>'title' ILIKE $1
                    AND metadata->>'season' = $2
                    AND metadata->>'episode'= $3
                ''',
                filter_show_name(backlog_item.metadata['show_title']),
                str(backlog_item.season),
                str(backlog_item.episode),
            )
        elif isinstance(backlog_item, MovieBacklogItem):
            results = await self._pool.fetch(
                '''
                    SELECT *
                    FROM torrentleech
                    WHERE metadata->>'type' = 'movie'
                    AND metadata->>'title' ILIKE $1
                    AND metadata->>'year' = $2
                ''',
                filter_show_name(backlog_item.metadata['movie_title']),
                str(backlog_item.metadata['year']),
            )
        else:
            results = []

        return [
            {
                'origin': self,
                'verified': True,
                'rank': result['seeders'],
                'title': result['title'],
                'media': {
                   'torrent:url': {
                       'url': result['link'],
                   },
                },
            }
            for result in results
        ]
