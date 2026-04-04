from __future__ import annotations

import asyncio
import logging
from typing import Optional

from telethon import TelegramClient as TelethonClient  # type: ignore[import-not-found]
from telethon.errors import (  # type: ignore[import-not-found]
    ChatWriteForbiddenError,
    FloodWaitError,
    RPCError,
)
from telethon.sessions import StringSession  # type: ignore[import-not-found]

logger = logging.getLogger(__name__)


class TelegramClient:
    def __init__(
        self, api_id: int, api_hash: str, session_string: Optional[str] = None
    ):
        if not isinstance(api_id, int):
            raise ValueError("api_id must be an integer")
        if not isinstance(api_hash, str) or not api_hash.strip():
            raise ValueError("api_hash must be a non-empty string")
        if session_string is not None and not isinstance(session_string, str):
            raise ValueError("session_string must be a string or None")

        self.api_id = api_id
        self.api_hash = api_hash.strip()
        self.session_string = session_string.strip() if session_string else None
        self._client: Optional[TelethonClient] = None
        self._max_retries = 3

    def _create_client(self) -> TelethonClient:
        session = (
            StringSession(self.session_string)
            if self.session_string
            else StringSession()
        )
        return TelethonClient(session, self.api_id, self.api_hash)

    async def start(self) -> None:
        if self._client is None:
            self._client = self._create_client()

        client = self._client
        assert client is not None

        logger.info("Starting Telegram client...")

        try:
            await client.connect()
            if not await client.is_user_authorized():
                raise RuntimeError(
                    "Telegram client is not authorized; provide TELEGRAM_SESSION_STRING"
                )

            me = await client.get_me()
            logger.info("Logged in as: %s (ID: %s)", me.first_name, me.id)
        except Exception:
            logger.error("Authentication error", exc_info=True)
            raise

    async def close(self) -> None:
        if self._client is not None:
            await self._client.disconnect()
            logger.info("Telegram client disconnected")

    async def send_message(self, chat_id: int, text: str) -> dict:
        if not isinstance(chat_id, int):
            return self._error_result("chat_id must be an integer")

        if not isinstance(text, str):
            return self._error_result("text must be a string")

        if not text.strip():
            return self._error_result("text must not be empty or whitespace-only")

        if len(text) > 4096:
            return self._error_result("text must be 4096 characters or fewer")

        if self._client is None:
            await self.start()

        client = self._client
        if client is None:
            return self._error_result("Telegram client is not initialized")

        last_error = "Unknown error"

        for attempt in range(self._max_retries + 1):
            try:
                entity = await client.get_entity(chat_id)
                message = await client.send_message(entity, text)
                message_id = int(getattr(message, "id", 0) or 0)

                logger.info(
                    "Telegram message sent successfully: chat_id=%s message_id=%s",
                    chat_id,
                    message_id,
                )
                return {
                    "ok": True,
                    "message_id": message_id,
                    "error": "",
                }

            except FloodWaitError as exc:
                wait_seconds = max(0, int(exc.seconds))
                last_error = f"Flood wait: retry after {wait_seconds} seconds"

                if attempt >= self._max_retries:
                    logger.error(
                        "Telegram flood wait exhausted: chat_id=%s wait_seconds=%s",
                        chat_id,
                        wait_seconds,
                    )
                    return self._error_result(last_error)

                logger.warning(
                    "Telegram flood wait: chat_id=%s retrying in %ss (attempt %s/%s)",
                    chat_id,
                    wait_seconds,
                    attempt + 1,
                    self._max_retries,
                )
                await asyncio.sleep(wait_seconds)

            except ChatWriteForbiddenError:
                last_error = "Chat write forbidden"
                logger.error(
                    "Telegram message failed: chat_id=%s error=%s", chat_id, last_error
                )
                return self._error_result(last_error)

            except (OSError, asyncio.TimeoutError, ConnectionError) as exc:
                last_error = str(exc) or exc.__class__.__name__
                logger.warning(
                    "Network error sending Telegram message: chat_id=%s error=%s",
                    chat_id,
                    last_error,
                    exc_info=True,
                )

                if attempt >= self._max_retries:
                    return self._error_result(last_error)

                backoff_seconds = 2**attempt
                await asyncio.sleep(backoff_seconds)

            except RPCError as exc:
                last_error = str(exc) or exc.__class__.__name__
                logger.error(
                    "Telegram RPC error: chat_id=%s error=%s",
                    chat_id,
                    last_error,
                    exc_info=True,
                )
                return self._error_result(last_error)

            except (ValueError, TypeError) as exc:
                last_error = str(exc) or exc.__class__.__name__
                logger.error(
                    "Invalid Telegram message parameters: chat_id=%s error=%s",
                    chat_id,
                    last_error,
                    exc_info=True,
                )
                return self._error_result(last_error)

            except Exception as exc:
                last_error = str(exc) or exc.__class__.__name__
                logger.error(
                    "Unexpected error sending Telegram message: chat_id=%s error=%s",
                    chat_id,
                    last_error,
                    exc_info=True,
                )
                if attempt >= self._max_retries:
                    return self._error_result(last_error)

                backoff_seconds = 2**attempt
                await asyncio.sleep(backoff_seconds)

        return self._error_result(last_error)

    def _error_result(self, error: str) -> dict:
        return {
            "ok": False,
            "message_id": 0,
            "error": error,
        }
