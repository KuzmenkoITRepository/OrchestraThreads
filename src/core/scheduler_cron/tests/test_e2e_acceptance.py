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
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

from aiohttp import web

from core.scheduler_cron.service_runtime import SchedulerCronService

_TEST_SCHEMA_PREFIX = "scheduler_e2e_"
_DELIVER_PATH = "/deliver"
_POLL_INTERVAL = 0.05
_MAX_WAIT_SECONDS = 10.0
_E2E_JOB_PREFIX = "e2e-svc"


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


class TestSchedulerCronServiceE2E(unittest.TestCase):  # noqa: WPS214 - acceptance flow keeps service lifecycle assertions in one fixture class  # noqa: WPS338
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

    def test_e2e_date_job_fires_and_records_run(self) -> None:
        """Boot real service, create date job, verify full chain."""
        self.loop.run_until_complete(self._service_e2e_flow())

    async def _service_e2e_flow(self) -> None:  # noqa: WPS217 - end-to-end setup needs multiple awaits across service lifecycle stages
        received: list[dict[str, object]] = []
        events_url, runner = await _start_fake_server(received)

        config: Any = _TestConfig(self.test_schema)
        service: Any = SchedulerCronService(config)

        with patch(
            "core.scheduler_cron.service_runtime._events_engine_url",
            return_value=events_url,
        ):
            await service.start()

        try:  # noqa: WPS501 - finally-only ensures cleanup of server, service, and schema
            await self._create_and_fire_job(service, received)
        finally:
            await _e2e_cleanup(service, runner, self)

    async def _create_and_fire_job(  # noqa: WPS217 - delivery scenario needs sequential awaits for create, trigger, and polling
        self,
        service: Any,
        received: list[dict[str, object]],
    ) -> None:
        job_id, job_name = await _create_e2e_job(service.store)
        job = await service.store.get_job_by_name(job_name)
        assert job is not None
        await service._engine.add_job(job)

        await _poll_until(received, _MAX_WAIT_SECONDS)
        self._assert_delivery(received)
        await self._assert_run_recorded(service.store, str(job_id), job_name)

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
        elapsed = _POLL_INTERVAL
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

        job = await store.get_job_by_name(job_name)
        if job is not None:
            run_count = int(job.get("run_count") or 0)
            self.assertGreaterEqual(run_count, 1)

    async def _drop_schema(self) -> None:
        import asyncpg  # noqa: WPS433 - local import keeps DB dependency scoped to schema teardown

        conn = await asyncpg.connect(_database_url())
        try:  # noqa: WPS501 - finally-only ensures connection close
            await conn.execute(f'DROP SCHEMA IF EXISTS "{self.test_schema}" CASCADE')
        finally:
            await conn.close()


async def _start_fake_server(
    received: list[dict[str, object]],
) -> tuple[str, web.AppRunner]:
    """Build fake events app, start server, return URL and runner."""

    async def handle_deliver(request: web.Request) -> web.Response:  # noqa: WPS430
        body = await request.json()
        received.append(body)
        return web.json_response({"accepted": True})

    app = web.Application()
    app.router.add_post(_DELIVER_PATH, handle_deliver)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    sockets = getattr(site._server, "sockets", None) or []
    assert sockets
    port: int = sockets[0].getsockname()[1]
    return f"http://127.0.0.1:{port}", runner


async def _create_e2e_job(store: Any) -> tuple[str, str]:
    """Create a date job scheduled 1s from now, return (job_id, name)."""
    job_suffix = uuid.uuid4().hex[:8]
    job_name = f"{_E2E_JOB_PREFIX}-{job_suffix}"
    fire_at = (datetime.now(UTC) + timedelta(seconds=1)).isoformat()
    job_id = await store.create_job(
        name=job_name,
        job_type="date",
        schedule=fire_at,
        action_type="agent_event",
        action_payload={"target_agent": "sgr", "event_data": {"task": "e2e"}},
        created_by="e2e-test",
    )
    return str(job_id), job_name


async def _poll_until(
    received: Sequence[object],
    max_seconds: float,
) -> None:
    """Wait until received is non-empty or timeout."""
    elapsed = _POLL_INTERVAL
    while elapsed < max_seconds and not received:
        await asyncio.sleep(_POLL_INTERVAL)
        elapsed += _POLL_INTERVAL


async def _e2e_cleanup(
    service: Any,
    runner: web.AppRunner,
    test: TestSchedulerCronServiceE2E,
) -> None:
    """Cleanup service, runner, and schema."""
    await service.stop()
    await runner.cleanup()
    await test._drop_schema()
