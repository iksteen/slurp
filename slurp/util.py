import configparser

import operator
import pkg_resources
import re
import logging

import guessit

logger = logging.getLogger(__name__)

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


def guess_media_info(title):
    try:
        info = guessit.guessit(title)
    except:
        logger.error('guessit failed to guess {}:'.format(title))
        return {}
    else:
        if isinstance(info.get('episode'), int):
            info['episode'] = [info['episode']]
        return info


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
