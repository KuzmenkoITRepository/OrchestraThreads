from __future__ import annotations

import asyncio
import os
import unittest
import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

from core.scheduler_cron.service_runtime import SchedulerCronService, build_app

_TEST_SCHEMA_PREFIX = "scheduler_svc_"
_BOOTSTRAP_PATH = "core.scheduler_cron.service_runtime.bootstrap_jobs"
_EXECUTOR_PATH = "core.scheduler_cron.service_runtime.JobExecutor"
_ENGINE_PATH = "core.scheduler_cron.service_runtime.SchedulerEngine"
_HTTP_OK = 200
_HTTP_UNAVAILABLE = 503


def _database_url() -> str:
    return os.getenv(
        "SCHEDULER_CRON_TEST_DATABASE_URL",
        os.getenv(
            "ORCHESTRA_THREADS_TEST_DATABASE_URL",
            "postgresql://orchestra:orchestra@postgres:5432/orchestra_threads",
        ),
    )


class _TestConfig:
    """Minimal config for service tests."""

    def __init__(self, schema: str) -> None:
        self.host = "127.0.0.1"
        self.port = 0
        self.database_url = _database_url()
        self.db_schema = schema


def _start_service_mocked(service: Any, run: Any) -> None:
    """Start service with executor, engine, and bootstrap mocked out."""
    with patch(_BOOTSTRAP_PATH, new_callable=AsyncMock):
        with patch(_EXECUTOR_PATH) as exc_cls:
            exc_cls.return_value = AsyncMock()
            with patch(_ENGINE_PATH) as eng_cls:
                eng_cls.return_value = AsyncMock()
                run(service.start())


async def _drop_schema_by_name(schema: str) -> None:
    import asyncpg  # noqa: WPS433 - local import keeps DB dependency scoped to schema teardown helper

    conn = await asyncpg.connect(_database_url())
    try:  # noqa: WPS501 - finally-only is correct here: connection must close regardless
        await conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
    finally:
        await conn.close()


class TestHealthzEndpoint(AioHTTPTestCase):
    """Test /healthz HTTP endpoint via aiohttp test client."""

    test_schema: str

    async def get_application(self) -> web.Application:
        self.test_schema = _TEST_SCHEMA_PREFIX + uuid.uuid4().hex[:8]
        config: Any = _TestConfig(self.test_schema)
        self._service: Any = SchedulerCronService(config)

        with patch(_BOOTSTRAP_PATH, new_callable=AsyncMock):
            with patch(_EXECUTOR_PATH) as exc_cls:
                exc_cls.return_value = AsyncMock()
                with patch(_ENGINE_PATH) as eng_cls:
                    eng_cls.return_value = AsyncMock()
                    await self._service.start()

        return build_app(self._service)

    async def tearDownAsync(self) -> None:
        await self._service.stop()
        await _drop_schema_by_name(self.test_schema)

    async def test_healthz_ok(self) -> None:
        resp = await self.client.request("GET", "/healthz")
        self.assertEqual(resp.status, _HTTP_OK)

    async def test_healthz_json(self) -> None:
        resp = await self.client.request("GET", "/healthz")
        body = await resp.json()
        self.assertEqual(body["status"], "ok")

    async def test_healthz_unhealthy(self) -> None:
        original_ping = self._service.store.ping
        self._service.store.ping = AsyncMock(return_value=False)
        try:  # noqa: WPS501 - finally-only restores mock; no exception handling needed
            resp = await self.client.request("GET", "/healthz")
        finally:
            self._service.store.ping = original_ping
        self.assertEqual(resp.status, _HTTP_UNAVAILABLE)
        body = await resp.json()
        self.assertEqual(body["status"], "error")


class TestServiceLifecycle(unittest.TestCase):
    """Test service start/stop lifecycle."""

    loop: asyncio.AbstractEventLoop
    test_schema: str

    @classmethod
    def setUpClass(cls) -> None:
        cls.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(cls.loop)
        cls.test_schema = _TEST_SCHEMA_PREFIX + uuid.uuid4().hex[:8]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.loop.close()
        asyncio.set_event_loop(None)

    def test_start_and_stop(self) -> None:
        schema = f"{self.test_schema}a"
        config: Any = _TestConfig(schema)
        service: Any = SchedulerCronService(config)

        _start_service_mocked(service, self._run)

        self.assertTrue(service._started)
        self._run(service.stop())
        self.assertFalse(service._started)
        self._run(_drop_schema_by_name(schema))

    def test_double_start_is_noop(self) -> None:
        schema = f"{self.test_schema}b"
        config: Any = _TestConfig(schema)
        service: Any = SchedulerCronService(config)

        with patch(_BOOTSTRAP_PATH, new_callable=AsyncMock):
            with patch(_EXECUTOR_PATH) as exc_cls:
                exc_cls.return_value = AsyncMock()
                with patch(_ENGINE_PATH) as eng_cls:
                    eng_cls.return_value = AsyncMock()
                    self._run(service.start())
                    self._run(service.start())

        self.assertTrue(service._started)
        self._run(service.stop())
        self._run(_drop_schema_by_name(schema))

    def test_stop_without_start_is_noop(self) -> None:
        config: Any = _TestConfig(f"{self.test_schema}c")
        service: Any = SchedulerCronService(config)
        self._run(service.stop())
        self.assertFalse(service._started)

    def test_is_healthy_after_start(self) -> None:
        schema = f"{self.test_schema}d"
        config: Any = _TestConfig(schema)
        service: Any = SchedulerCronService(config)

        _start_service_mocked(service, self._run)

        healthy = self._run(service.is_healthy())
        self.assertTrue(healthy)
        self._run(service.stop())
        self._run(_drop_schema_by_name(schema))

    def _run(self, awaitable: Any) -> Any:
        return self.loop.run_until_complete(awaitable)
