#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Rebulk object default builder
"""
from guessit import GuessItApi
from guessit.rules import *


def movie_rebulk_builder(config):
    """
    Default builder for main Rebulk object used by api.
    Default builder for main Rebulk object used by api but without the episode rules.
    :return: Main Rebulk object
    :rtype: Rebulk
    """
    def _config(name):
        return config.get(name, {})

    rebulk = Rebulk()

    common_words = frozenset(_config('common_words'))

    rebulk.rebulk(path(_config('path')))
    rebulk.rebulk(groups(_config('groups')))

    rebulk.rebulk(container(_config('container')))
    rebulk.rebulk(source(_config('source')))
    rebulk.rebulk(video_codec(_config('video_codec')))
    rebulk.rebulk(audio_codec(_config('audio_codec')))
    rebulk.rebulk(screen_size(_config('screen_size')))
    rebulk.rebulk(website(_config('website')))
    rebulk.rebulk(date(_config('date')))
    rebulk.rebulk(title(_config('title')))
    rebulk.rebulk(language(_config('language'), common_words))
    rebulk.rebulk(country(_config('country'), common_words))
    rebulk.rebulk(release_group(_config('release_group')))
    rebulk.rebulk(streaming_service(_config('streaming_service')))
    rebulk.rebulk(other(_config('other')))
    rebulk.rebulk(size(_config('size')))
    rebulk.rebulk(bit_rate(_config('bit_rate')))
    rebulk.rebulk(edition(_config('edition')))
    rebulk.rebulk(cds(_config('cds')))
    rebulk.rebulk(bonus(_config('bonus')))
    rebulk.rebulk(film(_config('film')))
    rebulk.rebulk(part(_config('part')))
    rebulk.rebulk(crc(_config('crc')))

    rebulk.rebulk(processors(_config('processors')))

    rebulk.rebulk(mimetype(_config('mimetype')))
    rebulk.rebulk(type_(_config('type')))

    def customize_properties(properties):
        """
        Customize default rebulk properties
        """
        count = properties['count']
        del properties['count']

        properties['season_count'] = count
        properties['episode_count'] = count

        return properties

    rebulk.customize_properties = customize_properties

    return rebulk


movie_api = GuessItApi()
movie_api.configure(rules_builder=movie_rebulk_builder)


def movie_guessit(string, options=None):
    """
    Retrieves all matches from string as a dict
    :param string: the filename or release name
    :type string: str
    :param options: the filename or release name
    :type options: str|dict
    :return:
    :rtype:
    """
    return movie_api.guessit(string, options)
