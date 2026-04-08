"""MCP tool handlers for edit_telegram_message and delete_telegram_message."""

from __future__ import annotations

import logging
from typing import Any

from telegram_mcp.edit_delete_pipeline import execute_delete, execute_edit
from telegram_mcp.mcp_protocol import Payloads, ensure_text
from telegram_mcp.message_store import MessageStore

logger = logging.getLogger(__name__)

JsonDict = dict[str, Any]


async def handle_edit(
    client: Any,
    store: MessageStore,
    chat_id: int,
    message_id: int,
    new_text: str,
) -> JsonDict:
    """Edit a message and update the store."""
    record = store.lookup(message_id, chat_id)
    if record is None:
        return Payloads.result({"ok": False, "error": f"Message {message_id} not found in store"})
    try:
        result = await execute_edit(client, chat_id, message_id, new_text)
    except Exception as exc:
        logger.error("Edit failed: %s", exc, exc_info=True)
        return Payloads.result({"ok": False, "error": str(exc)})
    store.update_text(message_id, chat_id, new_text)
    return Payloads.result(result)


async def handle_delete(
    client: Any,
    store: MessageStore,
    chat_id: int,
    message_id: int,
) -> JsonDict:
    """Delete a message and remove from store."""
    record = store.lookup(message_id, chat_id)
    if record is None:
        return Payloads.result({"ok": False, "error": f"Message {message_id} not found in store"})
    try:
        result = await execute_delete(client, chat_id, message_id)
    except Exception as exc:
        logger.error("Delete failed: %s", exc, exc_info=True)
        return Payloads.result({"ok": False, "error": str(exc)})
    store.delete_record(message_id, chat_id)
    return Payloads.result(result)


def parse_edit_args(arguments: JsonDict) -> tuple[int, str]:
    """Extract and validate edit tool arguments."""
    msg_id = arguments.get("message_id")
    if msg_id is None:
        raise RuntimeError("message_id is required")
    new_text = ensure_text(arguments.get("new_text"), field_name="new_text")
    return int(msg_id), new_text


def parse_delete_args(arguments: JsonDict) -> int:
    """Extract and validate delete tool arguments."""
    msg_id = arguments.get("message_id")
    if msg_id is None:
        raise RuntimeError("message_id is required")
    return int(msg_id)
