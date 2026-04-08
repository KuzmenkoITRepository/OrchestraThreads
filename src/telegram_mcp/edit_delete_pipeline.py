"""Telethon-level execution for message editing and deletion."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def execute_edit(
    client: Any,
    chat_id: int,
    message_id: int,
    new_text: str,
) -> dict[str, Any]:
    """Edit a previously sent message via Telethon."""
    entity = await client.get_entity(chat_id)
    await client.edit_message(entity, message_id, new_text)
    logger.info("Telegram message edited: message_id=%s", message_id)
    return {"ok": True, "message_id": message_id}


async def execute_delete(
    client: Any,
    chat_id: int,
    message_id: int,
) -> dict[str, Any]:
    """Delete a previously sent message via Telethon."""
    entity = await client.get_entity(chat_id)
    await client.delete_messages(entity, [message_id])
    logger.info("Telegram message deleted: message_id=%s", message_id)
    return {"ok": True, "message_id": message_id}
