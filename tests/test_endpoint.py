import pytest
from aiohttp import web
from async_timeout import timeout

from jticker_core import Candle, Interval
from jticker_stats.stats import Stat


async def wait_healthcheck(client):
    async with timeout(1):
        while True:
            response = await client("GET", "healthcheck", _raw=True)
            if response.status != web.HTTPOk.status_code:
                continue
            d = await response.json()
            if d["healthy"]:
                return d


@pytest.mark.asyncio
async def test_healthcheck(stats, client):
    async with stats:
        d = await wait_healthcheck(client)
        assert d == dict(healthy=True, version="TEST_VERSION")


@pytest.mark.asyncio
async def test_empty_stats(stats, client):
    async with stats:
        await wait_healthcheck(client)
        d = await client("GET", "stats")
        assert d == []


@pytest.mark.asyncio
async def test_static_stats(stats, client, timestamp_utc_minute_now, time_series):
    candles = []
    for ex in ("A", "B"):
        for symbol in ("BTCUSD", "ETHBTC"):
            for dt in range(3):
                c = Candle(
                    exchange=ex,
                    symbol=symbol,
                    interval=Interval.D_1,
                    timestamp=timestamp_utc_minute_now - 60 * 60 * 24 * dt,
                    open=1,
                    high=1,
                    low=1,
                    close=1,
                )
                candles.append(c)
    async with time_series:
        await time_series.migrate()
        await time_series.add_candles(candles)
    async with stats:
        await wait_healthcheck(client)
        items = await client("GET", "stats")
        assert len(items) == 4
        stat_info = [Stat.from_dict(i) for i in items]
        for i in stat_info:
            assert i.trading_pair.exchange in ("A", "B")
            assert i.trading_pair.symbol in ("BTCUSD", "ETHBTC")
            assert i.first.exchange == i.trading_pair.exchange
            assert i.first.symbol == i.trading_pair.symbol
            assert i.first.timestamp == timestamp_utc_minute_now - 60 * 60 * 24 * 2
            assert i.last.exchange == i.trading_pair.exchange
            assert i.last.symbol == i.trading_pair.symbol
            assert i.last.timestamp == timestamp_utc_minute_now


@pytest.mark.asyncio
async def test_dynamic_stats(stats, client, timestamp_utc_minute_now, time_series):
    c = Candle(
        exchange="A",
        symbol="CD",
        interval=Interval.D_1,
        timestamp=timestamp_utc_minute_now,
        open=1,
        high=1,
        low=1,
        close=1,
    )
    async with time_series:
        await time_series.migrate()
    async with stats:
        await wait_healthcheck(client)
        items = await client("GET", "stats")
        assert len(items) == 0

        await time_series.add_candles([c])
        async with timeout(1):
            while True:
                items = await client("GET", "stats")
                if items:
                    break
                await stats.sleep(0.01)
        assert len(items) == 1


@pytest.mark.asyncio
async def test_api_doc(stats, client):
    async with stats:
        response = await client("GET", "api/doc/", _raw=True)
        response.raise_for_status()
        html = await response.text()
        assert html
