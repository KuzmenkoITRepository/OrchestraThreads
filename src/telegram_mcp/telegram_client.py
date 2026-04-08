from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from typing import Any

from telethon import TelegramClient as TelethonClient
from telethon.sessions import StringSession

from telegram_mcp import SendAttempt, send_with_retries
from telegram_mcp.send_request import SendRequest, validate_message_text
from telegram_mcp.send_retry import rich_send_with_retries

logger = logging.getLogger(__name__)


class _RetryClientAdapter:
    def __init__(self, client: TelethonClient) -> None:
        self._client = client

    async def get_entity(self, chat_id: int) -> Any:
        return await self._client.get_entity(chat_id)

    async def send_message(self, entity: Any, text: str) -> Any:
        return await self._client.send_message(entity, text)


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
    def __init__(
        self,
        api_id: int,
        api_hash: str,
        session_string: str | None = None,
        max_retries: int = 3,
        timeout_seconds: float = 10.0,
    ):
        if not isinstance(api_id, int):
            raise ValueError("api_id must be an integer")
        if not isinstance(api_hash, str) or not api_hash.strip():
            raise ValueError("api_hash must be a non-empty string")

        self.api_id = api_id
        self.api_hash = api_hash.strip()
        self.session_string = session_string.strip() if session_string else None
        self._client: TelethonClient | None = None
        self._max_retries = max_retries
        self._timeout = timeout_seconds

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
        client = await self.require_client()
        if client is None:
            return {"ok": False, "message_id": 0, "error": "Telegram client is not initialized"}
        return await send_with_retries(
            SendAttempt(
                client=_RetryClientAdapter(client),
                chat_id=chat_id,
                text=text,
                attempt=0,
                max_retries=self._max_retries,
            )
        )

    async def send_rich(
        self,
        chat_id: int,
        request: SendRequest,
        *,
        on_flood_wait: Callable[[int], None] | None = None,
    ) -> dict[str, Any]:
        """Send a message with optional formatting, reply, or media."""
        text_error = validate_message_text(request.message)
        if text_error is not None:
            return {"ok": False, "message_id": 0, "error": text_error}
        client = await self.require_client()
        if client is None:
            return {"ok": False, "message_id": 0, "error": "Telegram client is not initialized"}
        return await rich_send_with_retries(
            client,
            chat_id,
            request,
            max_retries=self._max_retries,
            on_flood_wait=on_flood_wait,
        )

    async def require_client(self) -> TelethonClient | None:
        """Return the raw Telethon client, starting if needed."""
        if self._client is None:
            await self.start()
        return self._client

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
        return TelethonClient(
            session,
            self.api_id,
            self.api_hash,
            timeout=int(self._timeout),
        )
