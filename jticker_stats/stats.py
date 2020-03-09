import json
import time
from dataclasses import dataclass
from importlib import resources
from typing import Dict, List, Optional

import backoff
from addict import Dict as AdDict
from aiohttp import ClientError, web
from dataclasses_json import DataClassJsonMixin
from jibrel_aiohttp_swagger import setup_swagger
from loguru import logger
from mode import Service
from tqdm import tqdm

from jticker_core import (AbstractTimeSeriesStorage, Candle, Interval, Order, RawTradingPair,
                          TqdmLogFile, WebServer, blocking_file_io, inject, register)


@dataclass
class Stat(DataClassJsonMixin):
    trading_pair: RawTradingPair
    first: Candle
    last: Candle


@register(singleton=True, name="stats")
class StatsService(Service):

    @inject
    def __init__(self, web_server: WebServer, config: AdDict, version: str,
                 time_series: AbstractTimeSeriesStorage):
        super().__init__()
        self.web_server = web_server
        self.config = config
        self.time_series = time_series
        self.version = version
        self._configure_router()
        self._stats: Optional[List[Dict]] = None
        self._stack_size = int(self.config.time_series_stacked_requests_size)
        self._stack_interval = float(self.config.time_series_stacked_requests_interval)
        self._update_interval = float(self.config.time_series_update_interval)
        self._cache_path = self.config.stats_cache_file

    def _configure_router(self):
        r = self.web_server.app.router
        r.add_route("GET", "/stats", self._stats_handler)
        r.add_route("GET", "/healthcheck", self._healthcheck_handler)
        with resources.path("jticker_stats", "api-spec.yml") as path:
            setup_swagger(self.web_server.app, str(path))

    def on_init_dependencies(self):
        return [
            self.web_server,
            self.time_series,
        ]

    @blocking_file_io
    def load_stats(self):
        if self._cache_path and self._cache_path.exists():
            self._stats = json.loads(self._cache_path.read_text())

    @blocking_file_io
    def save_stats(self):
        if self._cache_path:
            self._cache_path.write_text(json.dumps(self._stats, indent=4))

    async def on_started(self):
        await self.load_stats()
        self._stats = await self._pull_time_series_stats(throttle=False)
        await self.save_stats()
        start_at = time.monotonic() + self._update_interval
        self.add_future(self._pull_time_series_stats_periodic(start_at))

    def _tp_stats_generator(self, tp: RawTradingPair):
        first_candle_query = yield self.time_series.query_candles(tp, limit=1, order=Order.ASC,
                                                                  group_interval=Interval.D_1)
        last_candle_query = yield self.time_series.query_candles(tp, limit=1, order=Order.DESC,
                                                                 group_interval=Interval.D_1)
        if not first_candle_query.result:
            return None
        return Stat(tp, first_candle_query.result[0], last_candle_query.result[0])

    @backoff.on_exception(
        backoff.constant,
        exception=ClientError,
        jitter=None,
        interval=1,
        max_time=60)
    async def _pull_time_series_stats(self, throttle=True) -> List[Dict]:
        tps = await self.time_series.get_trading_pairs()
        logger.info("pulled {} trading pairs", len(tps))
        gens = [self._tp_stats_generator(tp) for tp in tps]
        stats: List[Stat] = []
        with tqdm(total=len(gens), ncols=80, ascii=True, mininterval=10,
                  maxinterval=10, file=TqdmLogFile(logger=logger)) as pbar:
            while gens:
                stack, gens = gens[:self._stack_size], gens[self._stack_size:]
                results = await self.time_series.compose_generators(*stack)
                stats.extend(s for s in results if s is not None)
                pbar.update(len(stack))
                if throttle:
                    await self.sleep(self._stack_interval)
        raw_stats: List[Dict] = [s.to_dict(encode_json=True) for s in stats]
        logger.info("pulled {} stat records", len(raw_stats))
        return raw_stats

    async def _pull_time_series_stats_periodic(self, start_at: float):
        await self.sleep(max(0, start_at - time.monotonic()))
        while True:
            self._stats = await self._pull_time_series_stats()
            await self.save_stats()
            await self.sleep(self._update_interval)

    async def _stats_handler(self, request):
        if self._stats is None:
            raise web.HTTPServiceUnavailable(text="Stats are not ready")
        return web.json_response(self._stats)

    async def _healthcheck_handler(self, request):
        if self._stats is None:
            raise web.HTTPServiceUnavailable(text="Stats are not ready")
        return web.json_response(dict(
            healthy=True,
            version=self.version,
        ))
