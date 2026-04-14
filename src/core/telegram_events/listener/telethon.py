from __future__ import annotations

import logging
from importlib import import_module
from typing import Any, cast

logger = logging.getLogger(__name__)


def load_telethon() -> tuple[type[Any], Any]:
    telethon_module = import_module("telethon")
    telegram_client = telethon_module.TelegramClient
    telethon_events = telethon_module.events

    return cast(type[Any], telegram_client), telethon_events


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


async def send_text_message(client: Any, chat_id: str, message: str) -> int:
    """Send a text message with the connected Telethon client."""
    sent_message = await client.send_message(entity=int(chat_id), message=message)
    raw_message_id = getattr(sent_message, "id", 0)
    return int(raw_message_id or 0)
