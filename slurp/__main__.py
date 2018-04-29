import logging
import os

import aiohttp
import asyncio

import appdirs
import click
import configparser

from slurp.core import Core

DEFAULT_CONFIG_PATH = os.path.join(appdirs.user_config_dir('slurp', 'thegraveyard.org'), 'slurp.ini')


async def run(config, config_data, *, loop):
    async with aiohttp.ClientSession() as session:
        core = Core(config, config_data, session=session, loop=loop)
        await core.run()


@click.command()
@click.option('--config', '-c', default=DEFAULT_CONFIG_PATH, help='Path to configuration file.')
def main(config):
    logging.basicConfig(level=logging.INFO)
    config_dir = os.path.split(config)[0] or '.'
    os.makedirs(config_dir, exist_ok=True)
    config_data = configparser.ConfigParser(defaults={'here': config_dir})
    config_data.read(config)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(run(config, config_data, loop=loop))


if __name__ == '__main__':
    main()
