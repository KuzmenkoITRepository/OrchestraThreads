"""HTTP server for telegram-events: /healthz and /send endpoints."""

from __future__ import annotations

import logging
from typing import Any

from aiohttp import web

logger = logging.getLogger(__name__)

_MAX_MESSAGE_LENGTH = 4096
_HTTP_BAD_REQUEST = 400
_HTTP_SERVICE_UNAVAILABLE = 503
_HTTP_BAD_GATEWAY = 502
_OK_FIELD = "ok"
_ERROR_FIELD = "error"


async def healthz(request: web.Request) -> web.Response:
    """Return service health status."""
    return web.json_response({_OK_FIELD: True, "service": "telegram-events"})


async def send(request: web.Request) -> web.Response:
    """Send a Telegram message via the shared Telethon client."""
    client = request.app.get("telethon_client")
    if client is None:
        return web.json_response(
            {_OK_FIELD: False, _ERROR_FIELD: "Telethon client not initialized"},
            status=_HTTP_SERVICE_UNAVAILABLE,
        )
    try:
        body = await request.json()
    except Exception:
        return web.json_response(
            {_OK_FIELD: False, _ERROR_FIELD: "Invalid JSON body"},
            status=_HTTP_BAD_REQUEST,
        )
    return await _handle_send(client, body)


async def _handle_send(client: Any, body: dict[str, Any]) -> web.Response:
    """Validate and execute the send."""
    chat_id = body.get("chat_id")
    message = body.get("message")
    error = _validate_send_params(chat_id, message)
    if error:
        return web.json_response({_OK_FIELD: False, _ERROR_FIELD: error}, status=_HTTP_BAD_REQUEST)
    if not isinstance(chat_id, int):
        return web.json_response(
            {_OK_FIELD: False, _ERROR_FIELD: "chat_id must be an integer"},
            status=_HTTP_BAD_REQUEST,
        )
    if not isinstance(message, str):
        return web.json_response(
            {
                _OK_FIELD: False,
                _ERROR_FIELD: "message is required and must be a non-empty string",
            },
            status=_HTTP_BAD_REQUEST,
        )
    return await _execute_send(client, int(chat_id), str(message))


def _validate_send_params(chat_id: Any, message: Any) -> str | None:
    if chat_id is None:
        return "chat_id is required"
    if not isinstance(chat_id, int):
        return "chat_id must be an integer"
    if not message or not isinstance(message, str):
        return "message is required and must be a non-empty string"
    if len(message) > _MAX_MESSAGE_LENGTH:
        return f"message must be {_MAX_MESSAGE_LENGTH} characters or fewer"
    return None


async def _execute_send(client: Any, chat_id: int, message: str) -> web.Response:
    try:
        entity = await client.get_entity(chat_id)
    except Exception as exc:
        logger.error("Failed to resolve entity %s: %s", chat_id, exc)
        return web.json_response(
            {_OK_FIELD: False, _ERROR_FIELD: f"Failed to resolve chat: {exc}"},
            status=_HTTP_BAD_GATEWAY,
        )
    try:
        sent = await client.send_message(entity, message)
    except Exception as exc:
        logger.error("Failed to send message to %s: %s", chat_id, exc)
        return web.json_response(
            {_OK_FIELD: False, _ERROR_FIELD: f"Failed to send message: {exc}"},
            status=_HTTP_BAD_GATEWAY,
        )
    message_id = int(getattr(sent, "id", 0) or 0)
    logger.info("Sent message to chat_id=%s message_id=%s", chat_id, message_id)
    return web.json_response({_OK_FIELD: True, "message_id": message_id})


def build_app() -> web.Application:
    """Create the aiohttp application with routes."""
    app = web.Application()
    app.router.add_get("/healthz", healthz)
    app.router.add_post("/send", send)
    return app
