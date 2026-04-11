"""Integration tests for agent log analysis service closure."""

from __future__ import annotations

import asyncio
import unittest
import uuid
from importlib import import_module
from typing import Any, cast

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, TestClient, TestServer

from core.agent_log_analysis.service import AgentLogAnalysisService, build_app


def _fixtures() -> Any:
    return import_module("core.agent_log_analysis.tests.service_integration_fixtures")


def _support() -> Any:
    return import_module("core.agent_log_analysis.tests.service_integration_support")


class TestHealthzEndpoint(AioHTTPTestCase):
    """Verify health endpoint over disposable schema."""

    test_schema: str

    async def get_application(self) -> web.Application:
        fixtures = _fixtures()
        self.test_schema = fixtures.TEST_SCHEMA_PREFIX + uuid.uuid4().hex[:8]
        self._service = AgentLogAnalysisService(config=fixtures.config(self.test_schema))
        await self._service.start()
        self.addAsyncCleanup(self._service.stop)
        self.addAsyncCleanup(fixtures.drop_schema_by_name, self.test_schema)
        return build_app(self._service)

    async def test_healthz_ok(self) -> None:
        resp = await self.client.request("GET", "/healthz")
        self.assertEqual(resp.status, 200)

    async def test_healthz_json(self) -> None:
        resp = await self.client.request("GET", "/healthz")
        body = await resp.json()
        self.assertEqual(body["status"], "ok")

    async def test_healthz_unhealthy(self) -> None:
        await self._service.stop()
        resp = await self.client.request("GET", "/healthz")
        self.assertEqual(resp.status, 503)
        body = await resp.json()
        self.assertEqual(body["status"], "error")


class TestServiceLifecycle(unittest.TestCase):
    """Verify lifecycle and integration parity over a disposable schema."""

    loop: asyncio.AbstractEventLoop
    test_schema: str

    @classmethod
    def setUpClass(cls) -> None:
        fixtures = _fixtures()
        cls.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(cls.loop)
        cls.test_schema = fixtures.TEST_SCHEMA_PREFIX + uuid.uuid4().hex[:8]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.loop.close()
        asyncio.set_event_loop(None)

    def test_start_and_stop(self) -> None:
        fixtures = _fixtures()
        service = AgentLogAnalysisService(config=fixtures.config(f"{self.test_schema}a"))
        self._run(service.start())
        self.assertTrue(service.state.started)
        self._run(service.stop())
        self.assertFalse(service.state.started)
        self._run(fixtures.drop_schema_by_name(f"{self.test_schema}a"))

    def test_double_start_is_noop(self) -> None:
        fixtures = _fixtures()
        service = AgentLogAnalysisService(config=fixtures.config(f"{self.test_schema}b"))
        self._run(service.start())
        self._run(service.start())
        self.assertTrue(service.state.started)
        self._run(service.stop())
        self._run(fixtures.drop_schema_by_name(f"{self.test_schema}b"))

    def test_stop_without_start_is_noop(self) -> None:
        fixtures = _fixtures()
        service = AgentLogAnalysisService(config=fixtures.config(f"{self.test_schema}c"))
        self._run(service.stop())
        self.assertFalse(service.state.started)

    def test_is_healthy_after_start(self) -> None:
        fixtures = _fixtures()
        service = AgentLogAnalysisService(config=fixtures.config(f"{self.test_schema}d"))
        self._run(service.start())
        healthy = self._run(service.is_healthy())
        self.assertTrue(healthy)
        self._run(service.stop())
        self._run(fixtures.drop_schema_by_name(f"{self.test_schema}d"))

    def _run(self, awaitable: Any) -> Any:
        return self.loop.run_until_complete(awaitable)


class TestServiceIntegrationParity(unittest.TestCase):
    """Verify HTTP ingest and runtime parity over a disposable schema."""

    loop: asyncio.AbstractEventLoop
    test_schema: str

    @classmethod
    def setUpClass(cls) -> None:
        fixtures = _fixtures()
        cls.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(cls.loop)
        cls.test_schema = fixtures.TEST_SCHEMA_PREFIX + uuid.uuid4().hex[:8]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.loop.close()
        asyncio.set_event_loop(None)

    def test_http_ingest_runtime_parity(self) -> None:
        self._run(self._parity_flow(f"{self.test_schema}e"))

    def _run(self, awaitable: Any) -> Any:
        return self.loop.run_until_complete(awaitable)

    async def _parity_flow(self, schema: str) -> None:
        fixtures = _fixtures()
        service = AgentLogAnalysisService(config=fixtures.config(schema))
        await service.start()
        try:
            await self._run_client_flow(service)
        except BaseException:
            raise
        finally:
            await service.stop()
            await fixtures.drop_schema_by_name(schema)

    async def _run_client_flow(self, service: AgentLogAnalysisService) -> None:
        payload = cast(dict[str, object], _fixtures().sample_event_payload())
        async with TestServer(build_app(service)) as server:
            raw_client: TestClient[Any, Any]
            async with TestClient(server) as raw_client:
                body = await self._ingest_payload(
                    raw_client,
                    payload,
                )
                views = await _support().collect_runtime_views(service, payload)
        _assert_runtime_parity(body, payload, views)

    async def _ingest_payload(
        self,
        client: TestClient[Any, Any],
        payload: dict[str, object],
    ) -> dict[str, object]:
        async with client.post("/api/v1/events/ingest", json=payload) as response:
            self.assertEqual(response.status, 200)
            return cast(dict[str, object], await response.json())


def _assert_runtime_parity(
    body: dict[str, object],
    payload: dict[str, object],
    views: Any,
) -> None:
    runtime_assertions = _support().RuntimeAssertions
    runtime_assertions.ingest_response(body, "evt-1")
    stored_event = views.event["event"]
    assert isinstance(stored_event, dict)
    runtime_assertions.event_identity(stored_event, payload)
    runtime_assertions.event_content(stored_event)
    runtime_assertions.query_and_timeline(
        views,
        agent_slug="agent-a",
        event_id="evt-1",
    )
    runtime_assertions.correlation_chain(
        views,
        correlation_id="corr-1",
        event_id="evt-1",
    )
    runtime_assertions.aggregate(views, agent_slug="agent-a")
    runtime_assertions.raw_logs(views, agent_slug="agent-a")
