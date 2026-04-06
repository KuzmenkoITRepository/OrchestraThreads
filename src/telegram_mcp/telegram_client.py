from __future__ import annotations

import inspect
import logging
from typing import Any

from telethon import TelegramClient as TelethonClient
from telethon.sessions import StringSession

from telegram_mcp import SendAttempt, send_with_retries

logger = logging.getLogger(__name__)


def validate_send_inputs(chat_id: int, text: str) -> str | None:
    if not isinstance(chat_id, int):
        return "chat_id must be an integer"
    if not isinstance(text, str):
        return "text must be a string"
    if not text.strip():
        return "text must not be empty or whitespace-only"
    if len(text) > 4096:
        return "text must be 4096 characters or fewer"
    return None


async def ensure_client_started(client: TelethonClient) -> tuple[str, str]:
    await client.connect()
    is_authorized = await client.is_user_authorized()
    if not is_authorized:
        raise RuntimeError("Telegram client is not authorized; provide TELEGRAM_SESSION_STRING")
    me = await client.get_me()
    user_name = str(getattr(me, "first_name", "unknown"))
    user_id = str(getattr(me, "id", "unknown"))
    return user_name, user_id


class TelegramClient:
    def __init__(self, api_id: int, api_hash: str, session_string: str | None = None):
        if not isinstance(api_id, int):
            raise ValueError("api_id must be an integer")
        if not isinstance(api_hash, str) or not api_hash.strip():
            raise ValueError("api_hash must be a non-empty string")
        if session_string is not None and not isinstance(session_string, str):
            raise ValueError("session_string must be a string or None")

        self.api_id = api_id
        self.api_hash = api_hash.strip()
        self.session_string = session_string.strip() if session_string else None
        self._client: TelethonClient | None = None
        self._max_retries = 3

    async def close(self) -> None:
        client = self._client
        if client is None:
            return
        disconnect_result = client.disconnect()
        if inspect.isawaitable(disconnect_result):
            await disconnect_result
        logger.info("Telegram client disconnected")

    async def send_message(self, chat_id: int, text: str) -> dict[str, Any]:
        validation_error = validate_send_inputs(chat_id, text)
        if validation_error is not None:
            return {"ok": False, "message_id": 0, "error": validation_error}
        client = await self._require_client()
        if client is None:
            return {"ok": False, "message_id": 0, "error": "Telegram client is not initialized"}
        return await send_with_retries(
            SendAttempt(
                client=client,
                chat_id=chat_id,
                text=text,
                attempt=0,
                max_retries=self._max_retries,
            )
        )

    async def start(self) -> None:
        if self._client is None:
            self._client = self._create_client()
        client = self._client
        assert client is not None
        logger.info("Starting Telegram client...")
        user_name, user_id = await ensure_client_started(client)
        logger.info("Logged in as: %s (ID: %s)", user_name, user_id)

    def _create_client(self) -> TelethonClient:
        session = StringSession(self.session_string) if self.session_string else StringSession()
        return TelethonClient(session, self.api_id, self.api_hash)

    async def _require_client(self) -> TelethonClient | None:
        if self._client is None:
            await self.start()
        return self._client
