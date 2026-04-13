"""HTTP server for telegram-events: /healthz and /send endpoints."""

from __future__ import annotations

import logging
from typing import Any

from aiohttp import web

from core.telegram_events import _http_send_helpers as _send

logger = logging.getLogger(__name__)

_HTTP_SERVICE_UNAVAILABLE = 503
_OK_FIELD = "ok"
_ERROR_FIELD = "error"


async def healthz(request: web.Request) -> web.Response:
    """Return service health status."""
    return web.json_response({_OK_FIELD: True, "service": "telegram-events"})


async def send(request: web.Request) -> web.Response:
    """Send a Telegram message via the better-telegram-mcp relay."""
    bearer_token = request.app.get("bearer_token")
    if not bearer_token or not _require_bearer_token(request, str(bearer_token)):
        return web.json_response(
            {_OK_FIELD: False, _ERROR_FIELD: "Unauthorized"},
            status=401,
        )
    relay_url = request.app.get("relay_url")
    if not relay_url:
        return web.json_response(
            {_OK_FIELD: False, _ERROR_FIELD: "Relay not configured"},
            status=_HTTP_SERVICE_UNAVAILABLE,
        )
    try:
        body = await request.json()
    except Exception:
        return web.json_response(
            {_OK_FIELD: False, _ERROR_FIELD: "Invalid JSON body"},
            status=400,
        )
    return await _handle_send(relay_url, bearer_token, body)


def _require_bearer_token(request: web.Request, expected_token: str) -> bool:
    authorization = str(request.headers.get("Authorization") or "").strip()
    if not authorization.startswith("Bearer "):
        return False
    token = authorization.removeprefix("Bearer ").strip()
    return token == expected_token


async def _handle_send(
    relay_url: str,
    bearer_token: str,
    body: dict[str, Any],
) -> web.Response:
    """Validate and execute the send via relay MCP."""
    chat_id = body.get("chat_id")
    message = body.get("message")
    error = _send.validate_send_params(chat_id, message)
    if error is not None:
        return web.json_response(
            {_OK_FIELD: False, _ERROR_FIELD: error},
            status=400,
        )
    if not isinstance(chat_id, int):
        return web.json_response(
            {_OK_FIELD: False, _ERROR_FIELD: "chat_id must be an integer"},
            status=400,
        )
    if not isinstance(message, str):
        return web.json_response(
            {
                _OK_FIELD: False,
                _ERROR_FIELD: "message is required and must be a non-empty string",
            },
            status=400,
        )
    return await _send.execute_send_via_relay(relay_url, bearer_token, chat_id, message)


def build_app() -> web.Application:
    """Create the aiohttp application with routes."""
    app = web.Application()
    app.router.add_get("/healthz", healthz)
    app.router.add_post("/send", send)
    return app
