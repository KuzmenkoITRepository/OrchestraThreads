"""Telethon-level send execution for text, formatting, reply, and media."""

from __future__ import annotations

import base64
import logging
from typing import Any

from telegram_mcp.send_request import MediaPayload, SendRequest

logger = logging.getLogger(__name__)


async def execute_send(
    client: Any,
    chat_id: int,
    request: SendRequest,
) -> dict[str, Any]:
    """Execute a send request against a Telethon client."""
    entity = await client.get_entity(chat_id)
    if isinstance(entity, list):
        raise ValueError("Telegram entity lookup returned multiple results")
    if request.media is not None:
        return await _send_media(client, entity, request)
    return await _send_text(client, entity, request)


async def _send_text(
    client: Any,
    entity: Any,
    request: SendRequest,
) -> dict[str, Any]:
    message = await client.send_message(
        entity,
        request.message,
        parse_mode=_telethon_parse_mode(request.parse_mode),
        reply_to=request.reply_to_message_id,
    )
    return _success_result(message)


async def _send_media(
    client: Any,
    entity: Any,
    request: SendRequest,
) -> dict[str, Any]:
    media = request.media
    assert media is not None
    raw_content = _decode_media_bytes(media)
    caption = request.message if request.message.strip() else None
    message = await client.send_file(
        entity,
        raw_content,
        caption=caption,
        parse_mode=_telethon_parse_mode(request.parse_mode),
        reply_to=request.reply_to_message_id,
        force_document=media.media_type != "photo",
        file_name=media.filename,
    )
    return _success_result(message)


def _telethon_parse_mode(parse_mode: str | None) -> str | None:
    """Map our parse_mode to Telethon's expected values."""
    if parse_mode == "markdown":
        return "md"
    return parse_mode


def _decode_media_bytes(media: MediaPayload) -> bytes | str:
    """Return bytes for base64 or a file path string for file-source media."""
    if media.source == "file":
        return media.data
    try:
        return base64.b64decode(media.data)
    except Exception as exc:
        raise ValueError(f"Invalid base64 in media.data: {exc}") from exc


def _success_result(message: Any) -> dict[str, Any]:
    message_id = int(getattr(message, "id", 0) or 0)
    logger.info("Telegram message sent: message_id=%s", message_id)
    return {"ok": True, "message_id": message_id, "error": ""}
