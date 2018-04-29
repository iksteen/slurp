import configparser

import operator
import os
import pkg_resources
import re
import logging

import guessit

logger = logging.getLogger(__name__)


def format_episode_info(episode_info):
    return '{show_title} S{season:02d}E{episode:02d}'.format(
        show_title=episode_info['metadata']['show_title'],
        **episode_info
    )


def key_for_episode(episode_info):
    return episode_info['show_id'], episode_info['season'], episode_info['episode']


FILTER_STRIP_CHARS = re.compile(r'["()\[\]]')
FILTER_SPACE_CHARS = re.compile(r'[\'-.,_+:]')
FILTER_MULTIPLE_SPACES = re.compile(r'\s+')


def filter_show_name(title):
    global FILTER_SPACE_CHARS, FILTER_STRIP_CHARS, FILTER_MULTIPLE_SPACES
    return FILTER_MULTIPLE_SPACES.sub(
        ' ',
        FILTER_SPACE_CHARS.sub(
            ' ',
            FILTER_STRIP_CHARS.sub(
                '',
                title.lower()
            )
        )
    ).strip()


def guess_episode_info(title):
    try:
        info = guessit.guessit(title)
    except:
        logger.error('guessit failed to guess {}:'.format(title))
        return {}
    else:
        if isinstance(info.get('episode'), int):
            info['episode'] = [info['episode']]
        return info


def guess_episode_keys_for_path(path):
    filename = os.path.split(path)[1]

    info = guess_episode_info(filename)
    if info.get('type') != 'episode' or 'season' not in info or 'episode' not in info:
        info = guess_episode_info(path)
        if info.get('type') != 'episode' or 'season' not in info or 'episode' not in info:
            return []

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


def parse_option_list(s):
    return set([
        phrase for phrase in [
            phrase.strip().lower()
            for phrase in s.split(',')
        ] if phrase
    ])


def load_plugins(section_name, abc, default_priority, core, *args, **kwargs):
    config_section = {}
    try:
        config_section = dict(core.config.items('slurp.{}'.format(section_name)))
    except configparser.NoSectionError:
        pass
    except:
        logger.exception('Invalid [slurp.{}] configuration section.'.format(section_name))

    plugins = []
    for entrypoint in pkg_resources.iter_entry_points('slurp.plugins.{}'.format(section_name)):
        try:
            priority = int(config_section.get('priority.{}'.format(entrypoint.name), default_priority))
        except ValueError:
            logger.exception('Failed to parse downloader plugin priority')
        else:
            plugin_class = entrypoint.load()
            if not issubclass(plugin_class, abc):
                logger.error('{} does not implement {}'.format(plugin_class, abc))
                continue

            if priority:
                try:
                    plugin = plugin_class(core, *args, **kwargs)
                except:
                    logger.exception('Failed to load plugin:')
                else:
                    plugins.append((priority, plugin))

    return [plugin for priority, plugin in sorted(plugins, key=operator.itemgetter(0))]
