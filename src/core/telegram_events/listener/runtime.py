from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, cast

from core.telegram_events.listener.message_data import (
    extract_event_fields,
    extract_message_data,
)
from core.telegram_events.listener.session import build_session
from core.telegram_events.listener.telethon import (
    build_client,
    log_authenticated_user,
    new_message_event,
)

logger = logging.getLogger(__name__)

MessageHandler = Callable[[dict[str, Any]], Awaitable[None]]


class TelegramListener:
    """Listens to incoming Telegram messages and forwards them to secretary agent."""

    def __init__(
        self,
        api_id: int,
        api_hash: str,
        session_string: str | None = None,
        session_file: str | None = None,
        on_message: MessageHandler | None = None,
    ) -> None:
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_string = session_string
        self.session_file = session_file
        self.client: Any | None = None
        self.on_message = on_message

    async def start_client(self) -> Any:
        session = build_session(self.session_string, self.session_file)
        client = build_client(session, self.api_id, self.api_hash)
        self.client = client
        logger.info("Starting Telegram client...")
        await self._start_client(client)
        await log_authenticated_user(client)
        if not self.session_string and isinstance(session, str):
            self._log_session_string(client)
        client.add_event_handler(self._handle_message, new_message_event())
        return client

    async def start_and_run(self) -> None:
        client = await self.start_client()
        logger.info("Telegram listener started and waiting for messages...")
        await cast(Awaitable[None], client.run_until_disconnected())

    async def stop(self) -> None:
        client = self.client
        if client is None:
            return
        await client.disconnect()
        logger.info("Telegram client disconnected")

    async def _start_client(self, client: Any) -> None:
        try:
            await cast(Awaitable[None], client.start())
        except Exception as exc:
            logger.error("Authentication error: %s", exc, exc_info=True)
            raise

    def _log_session_string(self, client: Any) -> None:
        try:
            session_string = client.session.save()
        except Exception as exc:
            logger.warning("Could not save session string: %s", exc)
            return
        if session_string:
            logger.info("Session authenticated successfully!")
            logger.info("Save this to TELEGRAM_SESSION_STRING: %s", session_string)

    async def _handle_message(self, event: Any) -> None:
        try:
            message_data = extract_message_data(*await extract_event_fields(event))
        except Exception as exc:
            logger.error("Error handling message: %s", exc, exc_info=True)
            return
        logger.info(
            "Received message from %s in %s: %s...",
            message_data["sender_name"],
            message_data["chat_name"],
            str(message_data["text"])[:50],
        )
        if self.on_message:
            await self.on_message(message_data)
