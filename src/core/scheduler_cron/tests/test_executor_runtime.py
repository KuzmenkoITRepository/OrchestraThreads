from __future__ import annotations

import asyncio
import unittest
from typing import Any

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

from core.scheduler_cron.executor_runtime import JobExecutor

_DELIVER_PATH = "/deliver"


def _fake_deliver_handler(received: list[dict[str, object]]) -> Any:
    """Return an aiohttp handler that records POSTed JSON and returns ok."""

    async def handler(request: web.Request) -> web.Response:
        body = await request.json()
        received.append(body)
        return web.json_response({"accepted": True})

    return handler


def _error_handler(status: int) -> Any:
    """Return a handler that always responds with the given HTTP status."""

    async def handler(_request: web.Request) -> web.Response:
        return web.Response(status=status, text="error")

    return handler


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

    def _run(self, awaitable: Any) -> Any:
        return self.loop.run_until_complete(awaitable)

    def test_execute_before_start_raises(self) -> None:
        executor = JobExecutor("http://localhost:9999")
        with self.assertRaises(RuntimeError):
            self._run(executor.execute("agent_event", {}))

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


class TestJobExecutorAgentEvent(AioHTTPTestCase):
    """Test agent_event execution against a fake events-engine."""

    def setUp(self) -> None:
        super().setUp()
        self._received: list[dict[str, object]] = []

    async def get_application(self) -> web.Application:
        self._received = []
        app = web.Application()
        app.router.add_post(_DELIVER_PATH, _fake_deliver_handler(self._received))
        return app

    async def test_agent_event_posts_to_deliver(self) -> None:
        base_url = str(self.server.make_url(""))
        executor = JobExecutor(base_url)
        await executor.start()
        try:
            result = await executor.execute(
                "agent_event",
                {"target_agent": "sgr", "event_data": {"type": "test"}},
            )
            self.assertEqual(result["status"], "success")
            self.assertIn("result", result)
            self.assertIn("duration_ms", result)
            self.assertIsInstance(result["duration_ms"], int)
            self.assertEqual(len(self._received), 1)
            payload = self._received[0]
            self.assertEqual(payload["agent_slug"], "sgr")
            event_data: Any = payload["event_data"]
            self.assertIn("delivery_id", event_data)
            self.assertTrue(str(event_data["delivery_id"]).startswith("scheduler-"))
            events = event_data["events"]
            self.assertEqual(len(events), 1)
            evt = events[0]
            self.assertEqual(evt["from_agent_slug"], "scheduler_cron")
            self.assertEqual(evt["to_agent_slug"], "sgr")
            self.assertEqual(evt["event_kind"], "message")
            self.assertIn("message_text", evt)
            self.assertFalse(evt["requires_response"])
        finally:
            await executor.stop()

    async def test_agent_event_missing_target_raises(self) -> None:
        base_url = str(self.server.make_url(""))
        executor = JobExecutor(base_url)
        await executor.start()
        try:
            with self.assertRaises(ValueError):
                await executor.execute("agent_event", {"event_data": {}})
        finally:
            await executor.stop()


class TestJobExecutorSchedulerWakeup(AioHTTPTestCase):
    """Test scheduler_wakeup execution against a fake events-engine."""

    def setUp(self) -> None:
        super().setUp()
        self._received: list[dict[str, object]] = []

    async def get_application(self) -> web.Application:
        self._received = []
        app = web.Application()
        app.router.add_post(_DELIVER_PATH, _fake_deliver_handler(self._received))
        return app

    async def test_scheduler_wakeup_posts_to_deliver(self) -> None:
        base_url = str(self.server.make_url(""))
        executor = JobExecutor(base_url)
        await executor.start()
        try:
            result = await executor.execute(
                "scheduler_wakeup",
                {"task": "check_overdue", "target_agent": "sgr"},
            )
            self.assertEqual(result["status"], "success")
            self.assertEqual(len(self._received), 1)
            payload = self._received[0]
            self.assertEqual(payload["agent_slug"], "sgr")
            event_data: Any = payload["event_data"]
            self.assertIn("delivery_id", event_data)
            evt = event_data["events"][0]
            self.assertEqual(evt["from_agent_slug"], "scheduler_cron")
            self.assertEqual(evt["to_agent_slug"], "sgr")
            self.assertEqual(evt["event_kind"], "message")
            self.assertIn("check_overdue", evt["message_text"])
            self.assertFalse(evt["requires_response"])
        finally:
            await executor.stop()

    async def test_scheduler_wakeup_uses_default_target(self) -> None:
        base_url = str(self.server.make_url(""))
        executor = JobExecutor(base_url)
        await executor.start()
        try:
            result = await executor.execute(
                "scheduler_wakeup",
                {"task": "check_overdue"},
            )
            self.assertEqual(result["status"], "success")
            payload = self._received[0]
            self.assertEqual(payload["agent_slug"], "sgr")
        finally:
            await executor.stop()


class TestJobExecutorUnknownAction(AioHTTPTestCase):
    """Test unknown action_type raises ValueError."""

    async def get_application(self) -> web.Application:
        app = web.Application()
        app.router.add_post(_DELIVER_PATH, _fake_deliver_handler([]))
        return app

    async def test_unknown_action_type_raises(self) -> None:
        base_url = str(self.server.make_url(""))
        executor = JobExecutor(base_url)
        await executor.start()
        try:
            with self.assertRaises(ValueError):
                await executor.execute("bogus_type", {})
        finally:
            await executor.stop()


class TestJobExecutorHttpErrors(AioHTTPTestCase):
    """Test HTTP error propagation from events-engine."""

    async def get_application(self) -> web.Application:
        app = web.Application()
        app.router.add_post(_DELIVER_PATH, _error_handler(500))
        return app

    async def test_server_error_propagates(self) -> None:
        base_url = str(self.server.make_url(""))
        executor = JobExecutor(base_url)
        await executor.start()
        try:
            with self.assertRaises(Exception):  # noqa: B017  # aiohttp raises ClientResponseError
                await executor.execute(
                    "agent_event",
                    {"target_agent": "sgr", "event_data": {}},
                )
        finally:
            await executor.stop()
