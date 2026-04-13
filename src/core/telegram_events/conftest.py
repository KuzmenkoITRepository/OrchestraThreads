"""Pytest configuration for telegram events tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Protocol

from aiohttp import web
from aiohttp.test_utils import TestServer

from core.telegram_events import http_server


class AiohttpServerFactory(Protocol):
    """Create aiohttp test servers for a given application."""

    async def __call__(self, app: web.Application) -> TestServer:
        """Start a test server for the given app."""
        ...


class _ServerFactory:
    """Own aiohttp test servers and close them in fixture teardown."""

    def __init__(self) -> None:
        self._servers: list[TestServer] = []

    async def __call__(self, app: web.Application) -> TestServer:
        server = TestServer(app)
        await server.start_server()
        self._servers.append(server)
        return server

    async def close(self) -> None:
        while self._servers:
            await self._servers.pop().close()


class FakeRelayServer:
    """Simulate better-telegram-mcp relay and events-engine endpoints."""

    def __init__(self) -> None:
        self.app = web.Application()
        self.app.router.add_get("/events/telegram", self.handle_sse_stream)
        self.app.router.add_post("/mcp", self.handle_mcp_call)
        self._events_engine_app = web.Application()
        self._events_engine_app.router.add_post("/deliver", self.handle_deliver)
        self.sse_events: list[dict[str, Any]] = []
        self.mcp_calls: list[dict[str, Any]] = []
        self.delivered_payloads: list[dict[str, Any]] = []
        self.mcp_response: dict[str, Any] | None = None
        self.mcp_status: int | None = None

    async def handle_sse_stream(self, request: web.Request) -> web.StreamResponse:
        """Stream SSE events to the consumer."""
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return web.Response(status=401, text="Unauthorized")

        response = web.StreamResponse(status=200, reason="OK")
        response.headers["Content-Type"] = "text/event-stream"
        response.headers["Cache-Control"] = "no-cache"
        await response.prepare(request)

        payload = self._build_sse_payload()
        if payload:
            await response.write(payload.encode("utf-8"))

        await response.write_eof()
        return response

    async def handle_mcp_call(self, request: web.Request) -> web.Response:
        """Handle MCP tools/call requests."""
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return web.json_response({"error": "Unauthorized"}, status=401)

        payload = await request.json()
        self.mcp_calls.append(payload)

        if self.mcp_status is not None:
            return web.json_response({"error": "service unavailable"}, status=self.mcp_status)

        if self.mcp_response is not None:
            return web.json_response(self.mcp_response)

        return web.json_response(
            {
                "jsonrpc": "2.0",
                "id": payload.get("id", 1),
                "result": {"content": [{"text": {"structuredContent": {"messageId": 12345}}}]},
            }
        )

    async def handle_deliver(self, request: web.Request) -> web.Response:
        """Capture delivery payloads."""
        payload = await request.json()
        self.delivered_payloads.append(payload)
        return web.json_response({"ok": True})

    def _build_sse_payload(self) -> str:
        import json

        if not self.sse_events:
            return ""

        lines = [f"data: {json.dumps(event)}" for event in self.sse_events]
        return "\n\n".join([*lines, ""])


def _build_telegram_events_app(
    relay_server: TestServer,
    events_engine_server: TestServer,
) -> web.Application:
    """Build a telegram-events app wired to fake relay services."""
    app = http_server.build_app()
    app["relay_url"] = str(relay_server.make_url("/mcp"))
    app["bearer_token"] = "test-secret-token"
    app["events_engine_url"] = str(events_engine_server.make_url(""))
    app["target_agent_slug"] = "secretary"
    return app


@asynccontextmanager
async def open_aiohttp_server_factory() -> AsyncIterator[AiohttpServerFactory]:
    """Create and close aiohttp test servers within pytest-asyncio lifecycle."""
    factory = _ServerFactory()
    try:
        yield factory
    finally:
        await factory.close()


@asynccontextmanager
async def open_telegram_events_context() -> AsyncIterator[dict[str, Any]]:
    """Start the relay, events-engine, and telegram-events test stack."""
    async with open_aiohttp_server_factory() as aiohttp_server:
        fake_relay = FakeRelayServer()
        relay_server = await aiohttp_server(fake_relay.app)
        events_engine_server = await aiohttp_server(fake_relay._events_engine_app)
        telegram_events_server = await aiohttp_server(
            _build_telegram_events_app(relay_server, events_engine_server)
        )

        yield {
            "bearer_token": "test-secret-token",
            "fake_relay": fake_relay,
            "relay_server": relay_server,
            "events_engine_server": events_engine_server,
            "telegram_events_server": telegram_events_server,
        }
