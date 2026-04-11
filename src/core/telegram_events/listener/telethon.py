from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def load_telethon() -> tuple[type[Any], Any]:
    from telethon import TelegramClient, events

    return TelegramClient, events


def build_client(session: str | Any, api_id: int, api_hash: str) -> Any:
    telegram_client, _ = load_telethon()
    return telegram_client(session, api_id, api_hash)


def new_message_event() -> Any:
    _, telethon_events = load_telethon()
    return telethon_events.NewMessage(incoming=True)


async def log_authenticated_user(client: Any) -> None:
    from core.telegram_events.listener.message_data import extract_field

    me = await client.get_me()
    logger.info(
        "Logged in as: %s (ID: %s)",
        extract_field(me, "first_name"),
        extract_field(me, "id"),
    )
