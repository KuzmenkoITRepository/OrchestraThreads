from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, TypedDict
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import TestServer

from core.telegram_events.service.runtime import TelegramEventsService
from core.telegram_events.sse_event import SSEEvent

_TOKEN = "test-secret-token"
_SLUG = "secretary"
_TIMEOUT = 5.0


class _StackFixture(TypedDict):
    relay: _RelayApp
    engine: _EngineApp
    threads: _ThreadsApp
    relay_srv: TestServer
    engine_srv: TestServer
    threads_srv: TestServer


class _ServiceFixture(TypedDict):
    svc: TelegramEventsService
    task: asyncio.Task[None]
    base: str
    relay: _RelayApp
    engine: _EngineApp
    threads: _ThreadsApp


def _auth_ok(raw: Any) -> bool:
    return str(raw).strip() == f"Bearer {_TOKEN}"


class _RelayApp:
    def __init__(self) -> None:
        self.events_q: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self.sse_connected = asyncio.Event()
        self.mcp_calls: list[dict[str, Any]] = []
        self.clear_calls: list[dict[str, Any]] = []
        self.agent_reqs: list[str] = []
        self.app = web.Application()
        self.app.router.add_get("/events/telegram", self._handle_sse)
        self.app.router.add_post("/mcp", self._handle_mcp)
        self.app.router.add_get(
            "/api/v1/agents/{slug}/status",
            self._handle_agent_status,
        )
        self.app.router.add_post("/clear_context", self._handle_clear)

    async def _handle_sse(self, request: web.Request) -> web.StreamResponse:
        if not _auth_ok(request.headers.get("Authorization", "")):
            return web.Response(status=401, text="Unauthorized")
        resp = web.StreamResponse(status=200, reason="OK")
        resp.headers["Content-Type"] = "text/event-stream"
        resp.headers["Cache-Control"] = "no-cache"
        await resp.prepare(request)
        self.sse_connected.set()
        try:
            while True:
                data = await self.events_q.get()
                if data is None:
                    break
                await resp.write(f"data: {json.dumps(data)}\n\n".encode())
        except asyncio.CancelledError:
            raise
        return resp

    async def _handle_mcp(self, request: web.Request) -> web.Response:
        if not _auth_ok(request.headers.get("Authorization", "")):
            return web.json_response({"error": "Unauthorized"}, status=401)
        body = await request.json()
        self.mcp_calls.append(body)
        return web.json_response(
            {
                "jsonrpc": "2.0",
                "id": body.get("id", 1),
                "result": {"content": [{"text": {"structuredContent": {"messageId": 12345}}}]},
            }
        )

    async def _handle_agent_status(self, request: web.Request) -> web.Response:
        slug = request.match_info["slug"]
        self.agent_reqs.append(slug)
        return web.json_response(
            {
                "status": {
                    "health_status": {"ok": True},
                    "http_endpoint": str(request.url.origin()),
                }
            }
        )

    async def _handle_clear(self, request: web.Request) -> web.Response:
        body = await request.json()
        self.clear_calls.append(body)
        return web.json_response({"ok": True})


class _EngineApp:
    def __init__(self) -> None:
        self.deliveries: list[dict[str, Any]] = []
        self.received = asyncio.Event()
        self.app = web.Application()
        self.app.router.add_post("/deliver", self._handle_deliver)

    async def _handle_deliver(self, request: web.Request) -> web.Response:
        body = await request.json()
        self.deliveries.append(body)
        self.received.set()
        return web.json_response({"ok": True})


class _ThreadsApp:
    def __init__(self) -> None:
        self.registrations: list[dict[str, Any]] = []
        self.heartbeats: list[dict[str, Any]] = []
        self.messages: list[dict[str, Any]] = []
        self.received = asyncio.Event()
        self.app = web.Application()
        self.app.router.add_post("/agents/register", self._handle_register)
        self.app.router.add_post("/agents/heartbeat", self._handle_heartbeat)
        self.app.router.add_post("/api/v1/messages", self._handle_message)

    async def _handle_register(self, request: web.Request) -> web.Response:
        body = await request.json()
        self.registrations.append(body)
        return web.json_response({"ok": True, "agent_slug": body.get("agent_slug")})

    async def _handle_heartbeat(self, request: web.Request) -> web.Response:
        body = await request.json()
        self.heartbeats.append(body)
        return web.json_response({"ok": True})

    async def _handle_message(self, request: web.Request) -> web.Response:
        body = await request.json()
        self.messages.append(body)
        self.received.set()
        thread_id = body.get("thread_id") or f"thread-{len(self.messages)}"
        return web.json_response({"ok": True, "thread": {"thread_id": thread_id}})


def _get_base_url(svc: TelegramEventsService) -> str:
    runner = svc._http_runner
    if runner is None:
        raise RuntimeError("Not started")
    site = next(iter(runner.sites))
    server = getattr(site, "_server", None)
    if not server or not getattr(server, "sockets", None):
        raise RuntimeError("No sockets")
    return f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}"


def _make_msg_event() -> dict[str, Any]:
    return {
        "event_id": "evt-1",
        "event_type": "message",
        "occurred_at": "2024-01-01T12:00:00Z",
        "mode": "private",
        "account": "test",
        "update": {
            "message": {
                "id": 42,
                "from": {"id": 7, "first_name": "Bob"},
                "chat": {"id": 321, "title": "Chat"},
                "text": "Hello",
                "date": 1704067200,
            }
        },
    }


def _make_clear_event() -> dict[str, Any]:
    return {
        "event_id": "evt-2",
        "event_type": "message",
        "occurred_at": "2024-01-01T13:00:00Z",
        "mode": "private",
        "account": "test",
        "update": {
            "message": {
                "id": 43,
                "from": {"id": 8, "first_name": "Alice"},
                "chat": {"id": 321, "title": "Chat"},
                "text": "/clear",
                "date": 1704067800,
            }
        },
    }


@asynccontextmanager
async def _open_stack(
    aiohttp_server: Callable[[web.Application], Awaitable[TestServer]],
) -> AsyncIterator[_StackFixture]:
    relay = _RelayApp()
    engine = _EngineApp()
    threads = _ThreadsApp()
    relay_srv = await aiohttp_server(relay.app)
    engine_srv = await aiohttp_server(engine.app)
    threads_srv = await aiohttp_server(threads.app)
    yield {
        "relay": relay,
        "engine": engine,
        "threads": threads,
        "relay_srv": relay_srv,
        "engine_srv": engine_srv,
        "threads_srv": threads_srv,
    }


@asynccontextmanager
async def _run_service(stack: _StackFixture) -> AsyncIterator[_ServiceFixture]:
    relay_srv = stack["relay_srv"]
    engine_srv = stack["engine_srv"]
    threads_srv = stack["threads_srv"]
    svc = TelegramEventsService(
        bearer_token=_TOKEN,
        events_engine_url=str(engine_srv.make_url("")),
        threads_url=str(threads_srv.make_url("")),
        orchestra_agents_url=str(relay_srv.make_url("")),
        http_host="127.0.0.1",
        http_port=0,
    )
    task = asyncio.create_task(svc.start())
    await svc.register_agent(object(), _SLUG, str(relay_srv.make_url("/mcp")))
    await asyncio.wait_for(stack["relay"].sse_connected.wait(), timeout=_TIMEOUT)
    base = _get_base_url(svc)
    yield {
        "svc": svc,
        "task": task,
        "base": base,
        "relay": stack["relay"],
        "engine": stack["engine"],
        "threads": stack["threads"],
    }
    await svc.stop()
    stack["relay"].events_q.put_nowait(None)
    await asyncio.wait_for(task, timeout=_TIMEOUT)


def _assert_thread_registration(threads: _ThreadsApp) -> None:
    assert len(threads.registrations) == 1
    assert threads.registrations[0]["agent_slug"] == "telegram_events"
    assert threads.registrations[0]["base_url"].startswith("http://127.0.0.1:")
    assert not threads.registrations[0]["base_url"].endswith(":0")


def _assert_forwarded_message(threads: _ThreadsApp) -> None:
    assert len(threads.messages) == 1
    assert threads.messages[0]["from_agent_slug"] == "telegram_events"
    assert threads.messages[0]["to_agent_slug"] == _SLUG
    assert threads.messages[0]["client_request_id"] == "telegram_321_42"


def _assert_clear_delivery(service: _ServiceFixture) -> None:
    relay = service["relay"]
    engine = service["engine"]
    assert relay.agent_reqs == [_SLUG]
    assert len(relay.clear_calls) == 1
    assert engine.deliveries[0]["agent_slug"] == _SLUG


def _assert_clear_event_metadata(service: _ServiceFixture) -> None:
    event_data = service["engine"].deliveries[0]["event_data"]
    event = event_data["events"][0]
    assert event["event_kind"] == "telegram_message"
    assert event["metadata"]["command"] == "/clear"
    assert event["metadata"]["triggered_by"] == "telegram_events"
    assert event["metadata"]["chat_id"] == 321
    assert "Контекст очищен" in event["message_text"]


async def test_message_forwarded(
    aiohttp_server: Callable[[web.Application], Awaitable[TestServer]],
) -> None:
    async with _open_stack(aiohttp_server) as stack:
        async with _run_service(stack) as service:
            relay = service["relay"]
            threads = service["threads"]
            relay.events_q.put_nowait(_make_msg_event())
            await asyncio.wait_for(threads.received.wait(), timeout=_TIMEOUT)
            _assert_thread_registration(threads)
            _assert_forwarded_message(threads)


async def test_clear_resolves_and_delivers(
    aiohttp_server: Callable[[web.Application], Awaitable[TestServer]],
) -> None:
    async with _open_stack(aiohttp_server) as stack:
        async with _run_service(stack) as service:
            stack["relay"].events_q.put_nowait(_make_clear_event())
            await asyncio.wait_for(service["engine"].received.wait(), timeout=_TIMEOUT)
            _assert_clear_delivery(service)
            _assert_clear_event_metadata(service)


async def test_unknown_source_event_warns_and_drops(
    aiohttp_server: Callable[[web.Application], Awaitable[TestServer]],
) -> None:
    async with _open_stack(aiohttp_server) as stack:
        async with _run_service(stack) as service:
            unknown_event = _make_msg_event()
            warning_event = asyncio.Event()

            def _warning_side_effect(message: str, source: str) -> None:
                if (
                    message == "Dropping SSE event from unknown source MCP URL: %s"
                    and source == "http://unknown.test/mcp"
                ):
                    warning_event.set()

            with patch(
                "core.telegram_events.service.runtime_registry_support.logger.warning",
                side_effect=_warning_side_effect,
            ) as warning_mock:
                await service["svc"]._handle_sse_event(
                    SSEEvent(**unknown_event),
                    source_telegram_mcp_url="http://unknown.test/mcp",
                )

            await asyncio.wait_for(warning_event.wait(), timeout=_TIMEOUT)
            warning_mock.assert_called_once_with(
                "Dropping SSE event from unknown source MCP URL: %s",
                "http://unknown.test/mcp",
            )
            assert service["engine"].deliveries == []
            assert service["threads"].messages == []
