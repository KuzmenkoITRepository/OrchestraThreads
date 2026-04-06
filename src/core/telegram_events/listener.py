"""Telegram message listener for OrchestraThreads."""

import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, cast

from telethon import TelegramClient, events
from telethon.sessions import StringSession

logger = logging.getLogger(__name__)

MessageHandler = Callable[[dict[str, Any]], Awaitable[None]]


def _resolve_sender_name(
    first_name: str,
    last_name: str,
    title: Any,
    username: str | None,
) -> str:
    if first_name:
        if last_name:
            return f"{first_name} {last_name}"
        return first_name
    if title:
        return str(title)
    if username:
        return f"@{username}"
    return "Unknown"


class _ListenerOps:
    @staticmethod
    def extract_field(value: Any, name: str) -> Any:
        return getattr(value, name, None)

    @staticmethod
    def build_session(session_string: str | None, session_file: str | None) -> str | Any:
        if session_string:
            logger.info("Using session string from environment")
            return StringSession(session_string)
        if session_file:
            logger.info("Using session file: %s", session_file)
            return session_file
        default_path = "sessions/telegram.session"
        Path("sessions").mkdir(exist_ok=True)
        logger.info("Using default session file: %s", default_path)
        return default_path

    @staticmethod
    def extract_message_data(message: Any, sender: Any, chat: Any) -> dict[str, Any]:
        sender_name, username, user_id = _ListenerOps.extract_sender(sender)
        date_value = _ListenerOps.extract_field(message, "date")
        timestamp = date_value.isoformat() if date_value else None
        return {
            "chat_id": _ListenerOps.extract_chat_id(message),
            "chat_name": _ListenerOps.extract_chat_name(chat),
            "message_id": int(_ListenerOps.extract_field(message, "id") or 0),
            "sender_name": sender_name,
            "username": username,
            "user_id": user_id,
            "text": str(_ListenerOps.extract_field(message, "message") or ""),
            "timestamp": timestamp,
        }

    @staticmethod
    def extract_chat_id(message: Any) -> str:
        peer = _ListenerOps.extract_field(message, "peer_id")
        if peer is None:
            return "unknown"
        for field_name in ("channel_id", "user_id", "chat_id"):
            field_value = _ListenerOps.extract_field(peer, field_name)
            if field_value is not None:
                return str(field_value)
        return "unknown"

    @staticmethod
    def extract_chat_name(chat: Any) -> str:
        if chat is None:
            return "Unknown Chat"
        title = _ListenerOps.extract_field(chat, "title")
        if title:
            return str(title)
        first_name = str(_ListenerOps.extract_field(chat, "first_name") or "")
        last_name = str(_ListenerOps.extract_field(chat, "last_name") or "")
        if first_name and last_name:
            return f"{first_name} {last_name}"
        if first_name:
            return first_name
        return "Unknown Chat"

    @staticmethod
    def extract_sender(sender: Any) -> tuple[str, str | None, str | None]:
        if sender is None:
            return "Unknown", None, None
        user_id_raw = _ListenerOps.extract_field(sender, "id")
        user_id = None
        if user_id_raw is not None:
            user_id = str(user_id_raw)
        username_raw = _ListenerOps.extract_field(sender, "username")
        username = str(username_raw) if username_raw else None
        sender_name = _resolve_sender_name(
            first_name=str(_ListenerOps.extract_field(sender, "first_name") or ""),
            last_name=str(_ListenerOps.extract_field(sender, "last_name") or ""),
            title=_ListenerOps.extract_field(sender, "title"),
            username=username,
        )
        return sender_name, username, user_id

    @staticmethod
    async def extract_event_fields(event: Any) -> tuple[Any, Any, Any]:
        message = event.message
        sender = await event.get_sender()
        chat = await event.get_chat()
        return message, sender, chat


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

    async def start(self) -> None:
        session = _ListenerOps.build_session(self.session_string, self.session_file)
        client = TelegramClient(session, self.api_id, self.api_hash)
        self.client = client
        logger.info("Starting Telegram client...")
        await self._start_client(client)
        me = await client.get_me()
        me_name = _ListenerOps.extract_field(me, "first_name")
        me_id = _ListenerOps.extract_field(me, "id")
        logger.info("Logged in as: %s (ID: %s)", me_name, me_id)
        self._maybe_log_session(client, session)
        client.add_event_handler(self._handle_message, events.NewMessage(incoming=True))
        client.add_event_handler(self._handle_message, events.NewMessage(outgoing=True))
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

    def _maybe_log_session(self, client: Any, session: str | Any) -> None:
        if self.session_string:
            return
        if isinstance(session, str):
            self._log_session_string(client)

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
            message_data = _ListenerOps.extract_message_data(
                *await _ListenerOps.extract_event_fields(event),
            )
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
