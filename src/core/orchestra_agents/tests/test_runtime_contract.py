from __future__ import annotations

import json
import os
import socket
import unittest
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from aiohttp import ClientSession, ClientTimeout

from core.orchestra_agents.runtime import (
    BaseAgentBackend,
    EventDelivery,
    EventDeliveryResult,
    StandardAgentApplication,
)

_METHOD_GET = "GET"
_KEY_CONTEXT_ID = "context_id"
_HTTP_BAD_REQUEST = 400


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


class DummyBackend(BaseAgentBackend):
    async def handle_events(self, delivery: EventDelivery) -> EventDeliveryResult:
        self.remember_delivery(delivery)
        return EventDeliveryResult(
            accepted=True,
            accepted_events=len(delivery.events),
            delivery_id=delivery.delivery_id,
        )


class _RegisteringBackend(DummyBackend):
    def __init__(self) -> None:
        super().__init__(
            agent_slug="dummy_agent",
            backend_type="example",
            working_dir="/workspace",
        )
        self.on_start_calls = 0
        self.on_shutdown_calls = 0

    async def on_start(self) -> None:
        self.on_start_calls += 1

    async def on_shutdown(self) -> None:
        self.on_shutdown_calls += 1


class _DummyRunner:
    def __init__(self) -> None:
        self.setup = AsyncMock()
        self.cleanup = AsyncMock()


class _DummyResponse:
    def __init__(self, *, status_code: int = 200, payload: object | None = None) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {"ok": True}

    def json(self) -> object:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _DummyAsyncClient:
    def __init__(self, *, post: AsyncMock) -> None:
        self.post = post

    async def __aenter__(self) -> _DummyAsyncClient:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class RuntimeContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.backend = DummyBackend(
            agent_slug="dummy_agent",
            backend_type="example",
            working_dir="/workspace",
        )
        self.port = _free_port()
        self.app = StandardAgentApplication(backend=self.backend, host="127.0.0.1", port=self.port)
        await self.app.start()
        self.session = ClientSession(timeout=ClientTimeout(total=10))

    async def asyncTearDown(self) -> None:
        await self.session.close()
        await self.app.stop()

    async def test_health_endpoint_reports_context_id(self) -> None:
        health = await self._request(_METHOD_GET, "/healthz")
        self.assertEqual(health["status"], "ok")
        self.assertTrue(health[_KEY_CONTEXT_ID])

    async def test_event_and_status_endpoints(self) -> None:
        health = await self._request(_METHOD_GET, "/healthz")
        initial_context_id = health[_KEY_CONTEXT_ID]

        event_payload = {
            "delivery_id": "delivery-1",
            "events": [
                {
                    "event_id": "event-1",
                    "thread_id": "thread-1",
                    "event_kind": "message",
                    "from_agent_slug": "secretary",
                    "to_agent_slug": "dummy_agent",
                    "message_text": "Ping",
                }
            ],
        }
        event_result = await self._request("POST", "/event", event_payload)
        self.assertTrue(event_result["accepted"])
        self.assertEqual(event_result["accepted_events"], 1)

        status = await self._request(_METHOD_GET, "/last_status")
        self.assertEqual(status["last_delivery_id"], "delivery-1")
        self.assertEqual(status["last_event_kind"], "message")
        self.assertEqual(status[_KEY_CONTEXT_ID], initial_context_id)

    async def test_clear_context_endpoint(self) -> None:
        health = await self._request(_METHOD_GET, "/healthz")
        initial_context_id = health[_KEY_CONTEXT_ID]

        clear_result = await self._request("POST", "/clear_context", {"requested_by": "service"})
        self.assertTrue(clear_result["success"])
        self.assertEqual(clear_result["context_generation"], 1)
        self.assertEqual(clear_result["previous_context_id"], initial_context_id)
        self.assertNotEqual(clear_result[_KEY_CONTEXT_ID], initial_context_id)

    async def test_start_registers_only_after_site_start(self) -> None:
        backend = _RegisteringBackend()
        app = StandardAgentApplication(backend=backend, host="127.0.0.1", port=_free_port())
        app_runner = _DummyRunner()
        site = MagicMock()
        start_order: list[str] = []

        async def _site_start() -> None:
            start_order.append("site.start")

        post = AsyncMock(return_value=_DummyResponse())

        async def _post(*args: object, **kwargs: object) -> _DummyResponse:
            start_order.append("register")
            return cast(_DummyResponse, await post(*args, **kwargs))

        site.start = AsyncMock(side_effect=_site_start)

        with patch.dict(
            os.environ,
            {
                "BETTER_TELEGRAM_MCP_URL": "http://telegram-mcp/mcp/",
                "TELEGRAM_EVENTS_URL": "http://telegram-events/",
            },
            clear=False,
        ):
            with patch("core.orchestra_agents.runtime.app.web.AppRunner", return_value=app_runner):
                with patch("core.orchestra_agents.runtime.app.web.TCPSite", return_value=site):
                    with patch(
                        "core.orchestra_agents.runtime.app.httpx.AsyncClient",
                        return_value=_DummyAsyncClient(post=AsyncMock(side_effect=_post)),
                    ):
                        await app.start()

        self.assertEqual(backend.on_start_calls, 1)
        app_runner.setup.assert_awaited_once()
        site.start.assert_awaited_once()
        self.assertEqual(start_order, ["site.start", "register"])
        post.assert_awaited_once_with(
            "http://telegram-events/register",
            json={
                "agent_slug": "dummy_agent",
                "telegram_mcp_url": "http://telegram-mcp/mcp",
            },
        )

    async def test_start_propagates_registration_failure_after_bind(self) -> None:
        backend = _RegisteringBackend()
        app = StandardAgentApplication(backend=backend, host="127.0.0.1", port=_free_port())
        app_runner = _DummyRunner()
        site = MagicMock()
        site.start = AsyncMock()
        post = AsyncMock(side_effect=httpx.TransportError("register failed"))
        sleep = AsyncMock()

        with patch.dict(
            os.environ,
            {
                "BETTER_TELEGRAM_MCP_URL": "http://telegram-mcp/mcp/",
                "TELEGRAM_EVENTS_URL": "http://telegram-events/",
            },
            clear=False,
        ):
            with patch("core.orchestra_agents.runtime.app.web.AppRunner", return_value=app_runner):
                with patch("core.orchestra_agents.runtime.app.web.TCPSite", return_value=site):
                    with patch("core.orchestra_agents.runtime.app.asyncio.sleep", sleep):
                        with patch(
                            "core.orchestra_agents.runtime.app.httpx.AsyncClient",
                            return_value=_DummyAsyncClient(post=post),
                        ):
                            with self.assertRaisesRegex(
                                RuntimeError,
                                "telegram-events self-registration failed",
                            ):
                                await app.start()

        app_runner.setup.assert_awaited_once()
        site.start.assert_awaited_once()
        self.assertEqual(post.await_count, 5)
        self.assertEqual(sleep.await_count, 4)
        app_runner.cleanup.assert_awaited_once()
        self.assertEqual(backend.on_shutdown_calls, 1)
        self.assertIsNone(app.runner)

    async def test_start_retries_transient_registration_failure_then_succeeds(self) -> None:
        backend = _RegisteringBackend()
        app = StandardAgentApplication(backend=backend, host="127.0.0.1", port=_free_port())
        app_runner = _DummyRunner()
        site = MagicMock()
        site.start = AsyncMock()
        post = AsyncMock(side_effect=[httpx.ConnectError("dns"), _DummyResponse()])
        sleep = AsyncMock()

        with patch.dict(
            os.environ,
            {
                "BETTER_TELEGRAM_MCP_URL": "http://telegram-mcp/mcp/",
                "TELEGRAM_EVENTS_URL": "http://telegram-events/",
            },
            clear=False,
        ):
            with patch("core.orchestra_agents.runtime.app.web.AppRunner", return_value=app_runner):
                with patch("core.orchestra_agents.runtime.app.web.TCPSite", return_value=site):
                    with patch("core.orchestra_agents.runtime.app.asyncio.sleep", sleep):
                        with patch(
                            "core.orchestra_agents.runtime.app.httpx.AsyncClient",
                            return_value=_DummyAsyncClient(post=post),
                        ):
                            await app.start()

        site.start.assert_awaited_once()
        self.assertEqual(post.await_count, 2)
        sleep.assert_awaited_once()
        app_runner.cleanup.assert_not_awaited()
        self.assertEqual(backend.on_shutdown_calls, 0)
        self.assertIs(app.runner, app_runner)

    async def test_start_skips_registration_when_env_missing(self) -> None:
        backend = _RegisteringBackend()
        app = StandardAgentApplication(backend=backend, host="127.0.0.1", port=_free_port())
        app_runner = _DummyRunner()
        site = MagicMock()
        site.start = AsyncMock()
        client_ctor = MagicMock()

        with patch.dict(
            os.environ,
            {
                "BETTER_TELEGRAM_MCP_URL": "",
                "TELEGRAM_EVENTS_URL": "",
            },
            clear=False,
        ):
            with patch("core.orchestra_agents.runtime.app.web.AppRunner", return_value=app_runner):
                with patch("core.orchestra_agents.runtime.app.web.TCPSite", return_value=site):
                    with patch("core.orchestra_agents.runtime.app.httpx.AsyncClient", client_ctor):
                        await app.start()

        self.assertEqual(backend.on_start_calls, 1)
        app_runner.setup.assert_awaited_once()
        site.start.assert_awaited_once()
        client_ctor.assert_not_called()

    async def test_register_self_rejects_malformed_response(self) -> None:
        backend = _RegisteringBackend()
        app = StandardAgentApplication(backend=backend, host="127.0.0.1", port=_free_port())
        post = AsyncMock(return_value=_DummyResponse(payload={"ok": False}))
        sleep = AsyncMock()

        with patch.dict(
            os.environ,
            {
                "BETTER_TELEGRAM_MCP_URL": "http://telegram-mcp/mcp/",
                "TELEGRAM_EVENTS_URL": "http://telegram-events/",
            },
            clear=False,
        ):
            with patch("core.orchestra_agents.runtime.app.asyncio.sleep", sleep):
                with patch(
                    "core.orchestra_agents.runtime.app.httpx.AsyncClient",
                    return_value=_DummyAsyncClient(post=post),
                ):
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "telegram-events self-registration returned malformed response",
                    ):
                        await app._register_self()

        post.assert_awaited_once()
        sleep.assert_not_awaited()

    async def test_stop_endpoint(self) -> None:
        stop_result = await self._request("POST", "/stop", {"reason": "closed"})
        self.assertTrue(stop_result["success"])
        self.assertEqual(stop_result["stop_reason"], "closed")

    async def _request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        async with self.session.request(
            method,
            f"http://127.0.0.1:{self.port}{path}",
            json=payload,
        ) as response:
            raw = await response.text()
            parsed = json.loads(raw) if raw else {}
            if response.status >= _HTTP_BAD_REQUEST:
                raise AssertionError(f"{method} {path} -> {response.status}: {parsed}")
            return cast(dict[str, Any], parsed)
