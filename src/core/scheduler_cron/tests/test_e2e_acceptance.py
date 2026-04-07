"""End-to-end acceptance test for scheduler_cron.

Goes through the REAL ``SchedulerCronService.start()`` wiring path:
service creates store, executor, engine, and bootstraps jobs.
A ``date`` job is then created and the engine fires it through the
real ``JobExecutor`` into a fake events-engine HTTP server.
We verify: HTTP delivery, DB run record, and counter update.
"""

from __future__ import annotations

import asyncio
import os
import unittest
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

from aiohttp import web

from core.scheduler_cron.service_runtime import SchedulerCronService

_TEST_SCHEMA_PREFIX = "scheduler_e2e_"
_DELIVER_PATH = "/deliver"
_POLL_INTERVAL = 0.05
_MAX_WAIT_SECONDS = 10.0


def _database_url() -> str:
    return os.getenv(
        "SCHEDULER_CRON_TEST_DATABASE_URL",
        os.getenv(
            "ORCHESTRA_THREADS_TEST_DATABASE_URL",
            "postgresql://orchestra:orchestra@postgres:5432/orchestra_threads",
        ),
    )


class _TestConfig:
    """Config that points to test database and test schema."""

    def __init__(self, schema: str) -> None:
        self.host = "127.0.0.1"
        self.port = 0
        self.database_url = _database_url()
        self.db_schema = schema


class TestSchedulerCronServiceE2E(unittest.TestCase):  # noqa: WPS214
    """Full acceptance via SchedulerCronService.start() wiring path."""

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

    def _run(self, awaitable: Any) -> Any:
        return self.loop.run_until_complete(awaitable)

    def test_service_start_fires_date_job_and_records_run(self) -> None:
        """Boot real service, create date job, verify full chain."""
        self._run(self._service_e2e_flow())

    async def _service_e2e_flow(self) -> None:  # noqa: WPS217
        received: list[dict[str, object]] = []
        fake_app = _build_fake_events_app(received)
        runner = web.AppRunner(fake_app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        sockets = getattr(site._server, "sockets", None) or []
        assert sockets
        port: int = sockets[0].getsockname()[1]
        events_url = f"http://127.0.0.1:{port}"

        config: Any = _TestConfig(self.test_schema)
        service: Any = SchedulerCronService(config)

        with patch(
            "core.scheduler_cron.service_runtime._events_engine_url",
            return_value=events_url,
        ):
            await service.start()

        try:
            await self._create_and_fire_job(service, received)
        finally:
            await service.stop()
            await runner.cleanup()
            await self._drop_schema()

    async def _create_and_fire_job(  # noqa: WPS217
        self,
        service: Any,
        received: list[dict[str, object]],
    ) -> None:
        store = service.store
        engine = service._engine

        job_name = f"e2e-svc-{uuid.uuid4().hex[:8]}"
        fire_at = (datetime.now(UTC) + timedelta(seconds=1)).isoformat()

        job_id = await store.create_job(
            name=job_name,
            job_type="date",
            schedule=fire_at,
            action_type="agent_event",
            action_payload={"target_agent": "sgr", "event_data": {"task": "e2e"}},
            created_by="e2e-test",
        )

        job = await store.get_job_by_name(job_name)
        assert job is not None
        await engine.add_job(job)

        elapsed = 0.0
        while elapsed < _MAX_WAIT_SECONDS and not received:
            await asyncio.sleep(_POLL_INTERVAL)
            elapsed += _POLL_INTERVAL

        self._assert_delivery(received)
        await self._assert_run_recorded(store, str(job_id), job_name)

    def _assert_delivery(self, received: list[dict[str, object]]) -> None:
        self.assertGreaterEqual(len(received), 1)
        payload = received[0]
        self.assertEqual(payload["agent_slug"], "sgr")
        event_data: Any = payload["event_data"]
        self.assertIn("delivery_id", event_data)
        events = event_data["events"]
        self.assertEqual(len(events), 1)
        evt = events[0]
        self.assertEqual(evt["from_agent_slug"], "scheduler_cron")
        self.assertEqual(evt["to_agent_slug"], "sgr")
        self.assertEqual(evt["event_kind"], "message")
        self.assertIn("e2e", str(evt["message_text"]))

    async def _assert_run_recorded(
        self,
        store: Any,
        job_id: str,
        job_name: str,
    ) -> None:
        elapsed = 0.0
        history: list[Any] = []
        while elapsed < _MAX_WAIT_SECONDS:
            history = await store.get_run_history(job_id)
            if history:
                break
            await asyncio.sleep(_POLL_INTERVAL)
            elapsed += _POLL_INTERVAL

        self.assertGreaterEqual(len(history), 1)
        run = history[0]
        self.assertEqual(run["status"], "success")
        self.assertIsNotNone(run["finished_at"])

        await self._assert_run_count(store, job_name)

    async def _assert_run_count(self, store: Any, job_name: str) -> None:
        elapsed = 0.0
        run_count = 0
        while elapsed < _MAX_WAIT_SECONDS:
            job = await store.get_job_by_name(job_name)
            if job is not None:
                run_count = int(job.get("run_count") or 0)
                if run_count >= 1:
                    break
            await asyncio.sleep(_POLL_INTERVAL)
            elapsed += _POLL_INTERVAL
        self.assertGreaterEqual(run_count, 1)

    async def _drop_schema(self) -> None:
        import asyncpg  # noqa: WPS433

        conn = await asyncpg.connect(_database_url())
        try:
            await conn.execute(f'DROP SCHEMA IF EXISTS "{self.test_schema}" CASCADE')
        finally:
            await conn.close()


def _build_fake_events_app(received: list[dict[str, object]]) -> web.Application:
    async def handle_deliver(request: web.Request) -> web.Response:
        body = await request.json()
        received.append(body)
        return web.json_response({"accepted": True})

    app = web.Application()
    app.router.add_post(_DELIVER_PATH, handle_deliver)
    return app
