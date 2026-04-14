from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any, Protocol

from aiohttp import web

from core.telegram_events.relay_compat_http_support import write_sse_events
from core.telegram_events.relay_compat_payloads import build_health_payload


class RelayCompatServiceProtocol(Protocol):
    def subscribe(self) -> asyncio.Queue[str | None]: ...

    def unsubscribe(self, subscriber: asyncio.Queue[str | None]) -> None: ...

    async def handle_json_rpc(self, payload: dict[str, Any]) -> dict[str, Any]: ...


_RELAY_SERVICE_KEY = web.AppKey(
    "relay_service",
    RelayCompatServiceProtocol,
)
_BEARER_TOKEN_KEY = web.AppKey("bearer_token", str)


def build_relay_compat_app(
    service: RelayCompatServiceProtocol,
    bearer_token: str,
) -> web.Application:
    app = web.Application()
    app[_RELAY_SERVICE_KEY] = service
    app[_BEARER_TOKEN_KEY] = bearer_token
    app.router.add_get("/health", health)
    app.router.add_get("/events/telegram", events_telegram)
    app.router.add_post("/mcp", mcp)
    return app


async def health(request: web.Request) -> web.Response:
    return web.json_response(build_health_payload())


async def events_telegram(request: web.Request) -> web.StreamResponse:
    if not _authorized(request):
        return web.Response(status=401, text="Unauthorized")
    service = _service(request)
    subscriber = service.subscribe()
    response = web.StreamResponse(status=200, reason="OK")
    response.headers["Content-Type"] = "text/event-stream"
    response.headers["Cache-Control"] = "no-cache"
    await response.prepare(request)
    try:
        await write_sse_events(response, subscriber)
    except (ConnectionResetError, RuntimeError):
        service.unsubscribe(subscriber)
        return response
    service.unsubscribe(subscriber)
    with suppress(ConnectionResetError, RuntimeError):
        await response.write_eof()
    return response


async def mcp(request: web.Request) -> web.Response:
    if not _authorized(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)
    if not isinstance(payload, dict):
        return web.json_response({"error": "Invalid JSON body"}, status=400)
    response_payload = await _service(request).handle_json_rpc(payload)
    return web.json_response(response_payload)


def _authorized(request: web.Request) -> bool:
    expected_token = request.app[_BEARER_TOKEN_KEY]
    authorization = str(request.headers.get("Authorization") or "").strip()
    if not authorization.startswith("Bearer "):
        return False
    token = authorization.removeprefix("Bearer ").strip()
    return token == expected_token


def _service(request: web.Request) -> RelayCompatServiceProtocol:
    return request.app[_RELAY_SERVICE_KEY]
