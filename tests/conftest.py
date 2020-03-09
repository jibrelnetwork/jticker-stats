import pytest
from addict import Dict
from aiohttp import ClientSession, web

from jticker_core import WebServer, injector
from jticker_stats.stats import StatsService


@pytest.fixture(autouse=True, scope="session")
def config():
    config = Dict(
        time_series_host="127.0.0.1",
        time_series_port="8086",
        time_series_allow_migrations=True,
        time_series_default_row_limit="1000",
        time_series_client_timeout="10",
        web_host="127.0.0.1",
        web_port="8080",
        time_series_update_interval="0.1",
        time_series_stacked_requests_size="10",
        time_series_stacked_requests_interval="0",
        io_file_max_workers="1",

    )
    injector.register(lambda: config, name="config")
    injector.register(lambda: "TEST_VERSION", name="version")
    return config


@pytest.fixture
async def _web_app():
    return web.Application()


@pytest.fixture
async def _web_server(_web_app):
    return WebServer(web_app=_web_app)


@pytest.fixture
async def stats(time_series, clean_influx, config, _web_server):
    return StatsService(web_server=_web_server)


@pytest.fixture
def base_url(stats, config):
    host = config.web_host
    port = config.web_port
    return f"http://{host}:{port}"


@pytest.fixture
async def client(base_url, stats):
    async def request(method, path, *, _raw=False, **json):
        url = f"{base_url}/{path}"
        async with session.request(method, url, json=json) as response:
            await response.read()
            if _raw:
                return response
            else:
                assert response.status == 200
                return await response.json()
    async with ClientSession() as session:
        yield request
