"""Parse MCP arguments into a SendRequest and execute via the appropriate path."""

from __future__ import annotations

from typing import Any

from telegram_mcp.send_request import (
    MediaPayload,
    ParseMode,
    SendRequest,
    validate_media,
    validate_parse_mode,
)

JsonDict = dict[str, Any]


def parse_send_request(arguments: JsonDict, message: str) -> SendRequest:
    """Build a SendRequest from MCP tool arguments."""
    parse_mode = _extract_parse_mode(arguments)
    reply_to = _extract_reply_to(arguments)
    media = _extract_media(arguments)
    return SendRequest(
        message=message,
        parse_mode=parse_mode,
        reply_to_message_id=reply_to,
        media=media,
    )


def is_rich_request(request: SendRequest) -> bool:
    """True if the request uses formatting, reply, or media."""
    return (
        request.parse_mode is not None
        or request.reply_to_message_id is not None
        or request.media is not None
    )


def _extract_parse_mode(arguments: JsonDict) -> ParseMode:
    raw = str(arguments.get("parse_mode") or "").strip()
    if not raw:
        return None
    return validate_parse_mode(raw)


def _extract_reply_to(arguments: JsonDict) -> int | None:
    raw = arguments.get("reply_to_message_id")
    if raw is None:
        return None
    return int(raw)


def _extract_media(arguments: JsonDict) -> MediaPayload | None:
    raw = arguments.get("media")
    if not isinstance(raw, dict) or not raw:
        return None
    return validate_media(raw)
