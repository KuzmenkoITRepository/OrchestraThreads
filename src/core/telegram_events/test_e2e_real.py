"""E2E integration tests for TelegramEventsService with fake boundaries."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, TypedDict

import httpx
from aiohttp import web
from aiohttp.test_utils import TestServer

from core.telegram_events.service.runtime import TelegramEventsService

_TOKEN = "test-secret-token"
_SLUG = "secretary"
_TIMEOUT = 5.0


class _StackFixture(TypedDict):
    relay: _RelayApp
    engine: _EngineApp
    relay_srv: TestServer
    engine_srv: TestServer


class _ServiceFixture(TypedDict):
    svc: TelegramEventsService
    task: asyncio.Task[None]
    base: str
    relay: _RelayApp
    engine: _EngineApp


def _auth_ok(raw: Any) -> bool:
    """Check Bearer token matches expected value."""
    return str(raw).strip() == f"Bearer {_TOKEN}"


class _RelayApp:
    """Fake relay server simulating better-telegram-mcp."""

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
    """Fake events-engine server capturing deliveries."""

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


def _get_base_url(svc: TelegramEventsService) -> str:
    """Extract HTTP base URL from running service."""
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
    """Create fake relay and engine servers."""
    relay = _RelayApp()
    engine = _EngineApp()
    relay_srv = await aiohttp_server(relay.app)
    engine_srv = await aiohttp_server(engine.app)
    yield {"relay": relay, "engine": engine, "relay_srv": relay_srv, "engine_srv": engine_srv}


@asynccontextmanager
async def _run_service(stack: _StackFixture) -> AsyncIterator[_ServiceFixture]:
    """Start real TelegramEventsService with fake dependencies."""
    relay = stack["relay"]
    relay_srv = stack["relay_srv"]
    engine_srv = stack["engine_srv"]
    svc = TelegramEventsService(
        events_url=str(relay_srv.make_url("/events/telegram")),
        mcp_url=str(relay_srv.make_url("/mcp")),
        bearer_token=_TOKEN,
        events_engine_url=str(engine_srv.make_url("")),
        target_agent_slug=_SLUG,
        orchestra_agents_url=str(relay_srv.make_url("")),
        http_host="127.0.0.1",
        http_port=0,
    )
    task = asyncio.create_task(svc.start())
    await asyncio.wait_for(relay.sse_connected.wait(), timeout=_TIMEOUT)
    base = _get_base_url(svc)
    yield {"svc": svc, "task": task, "base": base, "relay": relay, "engine": stack["engine"]}
    await svc.stop()
    relay.events_q.put_nowait(None)
    await asyncio.wait_for(task, timeout=_TIMEOUT)


async def test_message_forwarded(
    aiohttp_server: Callable[[web.Application], Awaitable[TestServer]],
) -> None:
    """Test inbound message flow: SSE → telegram-events → events-engine."""
    async with _open_stack(aiohttp_server) as stack:
        async with _run_service(stack) as service:
            relay = service["relay"]
            engine = service["engine"]
            relay.events_q.put_nowait(_make_msg_event())
            await asyncio.wait_for(engine.received.wait(), timeout=_TIMEOUT)
            assert len(engine.deliveries) == 1
            assert engine.deliveries[0]["agent_slug"] == _SLUG


async def test_send_reaches_relay(
    aiohttp_server: Callable[[web.Application], Awaitable[TestServer]],
) -> None:
    """Test outbound send flow: /send → relay MCP."""
    async with _open_stack(aiohttp_server) as stack:
        async with _run_service(stack) as service:
            relay = service["relay"]
            async with httpx.AsyncClient() as http:
                resp = await http.post(
                    f"{service['base']}/send",
                    headers={"Authorization": f"Bearer {_TOKEN}"},
                    json={"chat_id": 999, "message": "hi"},
                )
            assert resp.status_code == 200
            assert resp.json()["ok"] is True
            assert len(relay.mcp_calls) == 1
            assert relay.mcp_calls[0]["method"] == "tools/call"


async def test_clear_resolves_and_delivers(
    aiohttp_server: Callable[[web.Application], Awaitable[TestServer]],
) -> None:
    """Test clear command flow: /clear → agent status → clear_context → delivery."""
    async with _open_stack(aiohttp_server) as stack:
        async with _run_service(stack) as service:
            relay = service["relay"]
            engine = service["engine"]
            relay.events_q.put_nowait(_make_clear_event())
            await asyncio.wait_for(engine.received.wait(), timeout=_TIMEOUT)
            assert relay.agent_reqs == [_SLUG]
            assert len(relay.clear_calls) == 1
            assert engine.deliveries[0]["agent_slug"] == _SLUG


async def test_send_requires_valid_token(
    aiohttp_server: Callable[[web.Application], Awaitable[TestServer]],
) -> None:
    """Test authentication enforcement."""
    async with _open_stack(aiohttp_server) as stack:
        async with _run_service(stack) as service:
            base = service["base"]
            async with httpx.AsyncClient() as http:
                r1 = await http.post(f"{base}/send", json={"chat_id": 1, "message": "x"})
                r2 = await http.post(
                    f"{base}/send",
                    headers={"Authorization": "Bearer bad"},
                    json={"chat_id": 1, "message": "x"},
                )
                r3 = await http.post(
                    f"{base}/send",
                    headers={"Authorization": f"Bearer {_TOKEN}"},
                    json={"chat_id": 1, "message": "x"},
                )
            assert r1.status_code == 401
            assert r2.status_code == 401
            assert r3.status_code == 200
