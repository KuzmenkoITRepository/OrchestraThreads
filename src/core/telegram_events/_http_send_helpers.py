"""HTTP helpers for telegram-events /send endpoint."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from aiohttp import web

logger = logging.getLogger(__name__)

_MAX_MESSAGE_LENGTH = 4096
_HTTP_BAD_REQUEST = 400
_HTTP_BAD_GATEWAY = 502
_OK_FIELD = "ok"
_ERROR_FIELD = "error"


def validate_send_params(chat_id: Any, message: Any) -> str | None:
    """Validate chat_id and message parameters."""
    if chat_id is None:
        return "chat_id is required"
    if not isinstance(chat_id, int):
        return "chat_id must be an integer"
    if not message or not isinstance(message, str):
        return "message is required and must be a non-empty string"
    if len(message) > _MAX_MESSAGE_LENGTH:
        return f"message must be {_MAX_MESSAGE_LENGTH} characters or fewer"
    return None


async def execute_send_via_relay(
    relay_url: str,
    bearer_token: str,
    chat_id: int,
    message: str,
) -> web.Response:
    """Send message through better-telegram-mcp MCP endpoint."""
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "Content-Type": "application/json",
    }
    json_rpc_body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "send_telegram_message",
            "arguments": {"chat_id": str(chat_id), "message": message},
        },
    }
    async with httpx.AsyncClient(trust_env=False) as client:
        try:
            response = await client.post(
                relay_url,
                headers=headers,
                json=json_rpc_body,
                timeout=30.0,
            )
        except Exception as exc:
            logger.error("Failed to reach relay at %s: %s", relay_url, exc)
            return web.json_response(
                {_OK_FIELD: False, _ERROR_FIELD: f"Relay connection failed: {exc}"},
                status=_HTTP_BAD_GATEWAY,
            )

    if response.status_code != 200:
        logger.error(
            "Relay returned status %s: %s",
            response.status_code,
            response.text,
        )
        return web.json_response(
            {_OK_FIELD: False, _ERROR_FIELD: f"Relay returned {response.status_code}"},
            status=_HTTP_BAD_GATEWAY,
        )

    return _parse_relay_response(response, chat_id)


def _parse_relay_response(response: httpx.Response, chat_id: int) -> web.Response:
    """Parse JSON-RPC response from relay."""
    try:
        result = response.json()
    except Exception as exc:
        logger.error("Failed to parse relay response: %s", exc)
        return web.json_response(
            {_OK_FIELD: False, _ERROR_FIELD: "Invalid response from relay"},
            status=_HTTP_BAD_GATEWAY,
        )

    if not isinstance(result, dict):
        logger.error("Relay response is not a dict")
        return web.json_response(
            {_OK_FIELD: False, _ERROR_FIELD: "Invalid response from relay"},
            status=_HTTP_BAD_GATEWAY,
        )

    message_id = _extract_message_id(result)
    logger.info("Sent message to chat_id=%s via relay", chat_id)
    return web.json_response({_OK_FIELD: True, "message_id": message_id})


def _extract_message_id(result: dict[str, Any]) -> int:
    """Extract message_id from JSON-RPC response, handling both content shapes."""
    result_data = result.get("result", {})
    content_list = result_data.get("content", [])
    return _first_message_id_from_content(content_list)


def _first_message_id_from_content(content_list: list[Any]) -> int:
    """Extract first message_id from content array."""
    for item in content_list:
        message_id = _extract_id_from_item(item)
        if message_id is not None:
            return message_id
    return 0


def _extract_id_from_item(item: Any) -> int | None:
    """Try multiple content shapes to find message_id."""
    if not isinstance(item, dict):
        return None
    text_data = item.get("text", {})
    if isinstance(text_data, dict):
        structured_id = text_data.get("structuredContent", {}).get("messageId")
        if isinstance(structured_id, int):
            return structured_id
        direct_id = text_data.get("message_id")
        if isinstance(direct_id, int):
            return direct_id
    if isinstance(text_data, str) and text_data:
        return _parse_id_from_text_string(text_data)
    return None


def _parse_id_from_text_string(text: str) -> int | None:
    """Attempt to parse message_id from text string."""
    try:
        return int(text.strip())
    except (ValueError, TypeError):
        return None
