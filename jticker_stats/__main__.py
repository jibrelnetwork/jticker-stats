import asyncio
from argparse import ArgumentParser
from pathlib import Path

import sentry_sdk
from addict import Dict
from loguru import logger

from jticker_core import Worker, configure_logging, ignore_aiohttp_ssl_eror, inject, register

from .stats import StatsService


@register(singleton=True)
def name():
    return "jticker-stats"


@register(singleton=True)
@inject
def parser(name, base_parser):
    parser = ArgumentParser(name, parents=[base_parser])
    parser.add_argument("--stats-cache-file", default=None, type=Path,
                        help="Stats cache file for fast warm start [default: %(default)s]")
    parser.add_argument("--time-series-update-interval", default=60 * 60 * 24,
                        help="Time series stats update interval [default: %(default)s]")
    parser.add_argument("--time-series-stacked-requests-size", default=10,
                        help="Time series stacked requests size [default: %(default)s]")
    parser.add_argument("--time-series-stacked-requests-interval", default=10,
                        help="Time series stacked requests interval [default: %(default)s]")
    return parser


@register(singleton=True)
@inject
def host(config: Dict) -> str:
    return config.web_host


@register(singleton=True)
@inject
def port(config: Dict) -> str:
    return config.web_port


@inject
def main(config: Dict, version: str, stats: StatsService):
    loop = asyncio.get_event_loop()
    ignore_aiohttp_ssl_eror(loop, "3.5.4")
    configure_logging()
    if config.sentry_dsn:
        sentry_sdk.init(config.sentry_dsn, release=version)
    logger.info("Jticker stats version {}, config {}", version, config)
    Worker(stats).execute_from_commandline()


main()
