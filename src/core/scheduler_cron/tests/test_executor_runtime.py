from __future__ import annotations

import asyncio
import unittest
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

from core.scheduler_cron.executor_runtime import JobExecutor

_DELIVER_PATH = "/deliver"
_ACTION_AGENT_EVENT = "agent_event"
_TARGET_AGENT_KEY = "target_agent"
_TARGET_SLUG = "sgr"
_EVENT_DATA = "event_data"
_WAKEUP_TASK = "check_overdue"
_HTTP_INTERNAL_ERROR = 500


def _make_recording_app(received: list[dict[str, object]]) -> web.Application:
    """Build an aiohttp app that records POSTs to /deliver."""

    async def record_request(request: web.Request) -> web.Response:  # noqa: WPS430
        body = await request.json()
        received.append(body)
        return web.json_response({"accepted": True})

    app = web.Application()
    app.router.add_post(_DELIVER_PATH, record_request)
    return app


@asynccontextmanager
async def _executor_session(base_url: str) -> AsyncIterator[JobExecutor]:
    """Start executor, yield it, and guarantee stop."""
    executor = JobExecutor(base_url)
    await executor.start()
    try:
        yield executor
    finally:
        await executor.stop()


def _first_event(payload: dict[str, object]) -> dict[str, object]:
    event_data: Any = payload[_EVENT_DATA]
    return event_data["events"][0]  # type: ignore[no-any-return]


class TestJobExecutorLifecycle(unittest.TestCase):
    """Test start/stop and not-started guard."""

    loop: asyncio.AbstractEventLoop

    @classmethod
    def setUpClass(cls) -> None:
        cls.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(cls.loop)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.loop.close()
        asyncio.set_event_loop(None)

    def test_execute_before_start_raises(self) -> None:
        executor = JobExecutor("http://localhost:9999")
        with self.assertRaises(RuntimeError):
            self._run(executor.execute(_ACTION_AGENT_EVENT, {}))

    def test_start_and_stop(self) -> None:
        executor = JobExecutor("http://localhost:9999")
        self._run(executor.start())
        self.assertIsNotNone(executor._session)
        self._run(executor.stop())
        self.assertIsNone(executor._session)

    def test_double_stop_is_safe(self) -> None:
        executor = JobExecutor("http://localhost:9999")
        self._run(executor.start())
        self._run(executor.stop())
        self._run(executor.stop())

    def _run(self, awaitable: Any) -> Any:
        return self.loop.run_until_complete(awaitable)


class TestAgentEvent(AioHTTPTestCase):  # noqa: WPS214 - agent_event tests cover result, payload, event-item, and error cases
    """Test agent_event execution against a fake events-engine."""

    def setUp(self) -> None:
        super().setUp()
        self._received: list[dict[str, object]] = []

    async def get_application(self) -> web.Application:
        self._received = []
        return _make_recording_app(self._received)

    async def test_result_fields(self) -> None:
        async with self._session() as executor:
            got = await executor.execute(
                _ACTION_AGENT_EVENT,
                {_TARGET_AGENT_KEY: _TARGET_SLUG, _EVENT_DATA: {"type": "test"}},
            )
        self.assertEqual(got["status"], "success")
        self.assertIn("result", got)
        self.assertIn("duration_ms", got)
        self.assertIsInstance(got["duration_ms"], int)

    async def test_payload_delivery(self) -> None:
        async with self._session() as executor:
            await executor.execute(
                _ACTION_AGENT_EVENT,
                {_TARGET_AGENT_KEY: _TARGET_SLUG, _EVENT_DATA: {"type": "test"}},
            )
        self.assertEqual(len(self._received), 1)
        payload = self._received[0]
        self.assertEqual(payload["agent_slug"], _TARGET_SLUG)
        event_data: Any = payload[_EVENT_DATA]
        self.assertIn("delivery_id", event_data)
        delivery_id = str(event_data["delivery_id"])
        self.assertTrue(delivery_id.startswith("scheduler-"))

    async def test_event_item(self) -> None:
        async with self._session() as executor:
            await executor.execute(
                _ACTION_AGENT_EVENT,
                {_TARGET_AGENT_KEY: _TARGET_SLUG, _EVENT_DATA: {"type": "test"}},
            )
        evt = _first_event(self._received[0])
        self.assertEqual(evt["from_agent_slug"], "scheduler_cron")
        self.assertEqual(evt["to_agent_slug"], _TARGET_SLUG)
        self.assertEqual(evt["event_kind"], "message")
        self.assertIn("message_text", evt)
        self.assertFalse(evt["requires_response"])

    async def test_missing_target_raises(self) -> None:
        async with self._session() as executor:
            with self.assertRaises(ValueError):
                await executor.execute(_ACTION_AGENT_EVENT, {_EVENT_DATA: {}})

    async def test_unknown_action_raises(self) -> None:
        async with self._session() as executor:
            with self.assertRaises(ValueError):
                await executor.execute("bogus_type", {})

    def _session(self) -> AbstractAsyncContextManager[JobExecutor]:
        return _executor_session(str(self.server.make_url("")))


class TestSchedulerWakeup(AioHTTPTestCase):
    """Test scheduler_wakeup execution against a fake events-engine."""

    def setUp(self) -> None:
        super().setUp()
        self._received: list[dict[str, object]] = []

    async def get_application(self) -> web.Application:
        self._received = []
        return _make_recording_app(self._received)

    async def test_wakeup_result(self) -> None:
        async with self._session() as executor:
            got = await executor.execute(
                "scheduler_wakeup",
                {"task": _WAKEUP_TASK, _TARGET_AGENT_KEY: _TARGET_SLUG},
            )
        self.assertEqual(got["status"], "success")

    async def test_wakeup_payload(self) -> None:
        async with self._session() as executor:
            await executor.execute(
                "scheduler_wakeup",
                {"task": _WAKEUP_TASK, _TARGET_AGENT_KEY: _TARGET_SLUG},
            )
        payload = self._received[0]
        self.assertEqual(payload["agent_slug"], _TARGET_SLUG)
        evt = _first_event(payload)
        self.assertEqual(evt["from_agent_slug"], "scheduler_cron")
        self.assertEqual(evt["to_agent_slug"], _TARGET_SLUG)
        self.assertEqual(evt["event_kind"], "message")
        self.assertIn(_WAKEUP_TASK, str(evt["message_text"]))
        self.assertFalse(evt["requires_response"])

    async def test_wakeup_default_target(self) -> None:
        async with self._session() as executor:
            got = await executor.execute(
                "scheduler_wakeup",
                {"task": _WAKEUP_TASK},
            )
        self.assertEqual(got["status"], "success")
        self.assertEqual(self._received[0]["agent_slug"], _TARGET_SLUG)

    def _session(self) -> AbstractAsyncContextManager[JobExecutor]:
        return _executor_session(str(self.server.make_url("")))


class TestHttpErrors(AioHTTPTestCase):
    """Test HTTP error propagation from events-engine."""

    async def get_application(self) -> web.Application:
        async def error_handler(_request: web.Request) -> web.Response:  # noqa: WPS430
            return web.Response(status=_HTTP_INTERNAL_ERROR, text="error")

        app = web.Application()
        app.router.add_post(_DELIVER_PATH, error_handler)
        return app

    async def test_server_error_propagates(self) -> None:
        async with self._session() as executor:
            with self.assertRaises(Exception):  # noqa: B017  # aiohttp raises ClientResponseError
                await executor.execute(
                    _ACTION_AGENT_EVENT,
                    {_TARGET_AGENT_KEY: _TARGET_SLUG, _EVENT_DATA: {}},
                )

    def _session(self) -> AbstractAsyncContextManager[JobExecutor]:
        return _executor_session(str(self.server.make_url("")))
