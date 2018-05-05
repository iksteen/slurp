#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Rebulk object default builder
"""
from guessit import GuessItApi
from guessit.rules import *


def movie_rebulk_builder():
    """
    Default builder for main Rebulk object used by api but without the episode rules.
    :return: Main Rebulk object
    :rtype: Rebulk
    """
    rebulk = Rebulk()

    rebulk.rebulk(path())
    rebulk.rebulk(groups())

    rebulk.rebulk(container())
    rebulk.rebulk(format_())
    rebulk.rebulk(video_codec())
    rebulk.rebulk(audio_codec())
    rebulk.rebulk(screen_size())
    rebulk.rebulk(website())
    rebulk.rebulk(date())
    rebulk.rebulk(title())
    rebulk.rebulk(language())
    rebulk.rebulk(country())
    rebulk.rebulk(release_group())
    rebulk.rebulk(streaming_service())
    rebulk.rebulk(other())
    rebulk.rebulk(size())
    rebulk.rebulk(edition())
    rebulk.rebulk(cds())
    rebulk.rebulk(film())
    rebulk.rebulk(part())
    rebulk.rebulk(crc())

    rebulk.rebulk(processors())

    rebulk.rebulk(mimetype())
    rebulk.rebulk(type_())

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


movie_api = GuessItApi(movie_rebulk_builder())


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
