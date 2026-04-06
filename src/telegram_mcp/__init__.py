"""Telegram MCP server for sending messages via Telegram Bot API."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Protocol

from telethon.errors import ChatWriteForbiddenError, FloodWaitError, RPCError

logger = logging.getLogger(__name__)


class TelegramSendClient(Protocol):
    async def get_entity(self, chat_id: int) -> Any: ...

    async def send_message(self, entity: Any, text: str) -> Any: ...


@dataclass(frozen=True)
class SendAttempt:
    client: TelegramSendClient
    chat_id: int
    text: str
    attempt: int
    max_retries: int


async def send_with_retries(send_attempt: SendAttempt) -> dict[str, Any]:
    try:
        return await _send_once(send_attempt)
    except FloodWaitError as exc:
        wait_seconds = max(0, int(exc.seconds))
        error_text = f"Flood wait: retry after {wait_seconds} seconds"
        logger.warning(
            "Telegram flood wait: chat_id=%s retrying in %ss (attempt %s/%s)",
            send_attempt.chat_id,
            wait_seconds,
            send_attempt.attempt + 1,
            send_attempt.max_retries,
        )
        return await _retry_or_fail(send_attempt, wait_seconds, error_text)
    except Exception as exc:
        return await _handle_send_error(send_attempt, exc)


async def _send_once(send_attempt: SendAttempt) -> dict[str, Any]:
    entity = await send_attempt.client.get_entity(send_attempt.chat_id)
    if isinstance(entity, list):
        raise ValueError("Telegram entity lookup returned multiple results")
    message = await send_attempt.client.send_message(entity, send_attempt.text)
    message_id = int(getattr(message, "id", 0) or 0)
    logger.info(
        "Telegram message sent successfully: chat_id=%s message_id=%s",
        send_attempt.chat_id,
        message_id,
    )
    return {"ok": True, "message_id": message_id, "error": ""}


async def _handle_send_error(send_attempt: SendAttempt, exc: Exception) -> dict[str, Any]:
    error_text = str(exc) or exc.__class__.__name__
    if isinstance(exc, ChatWriteForbiddenError):
        logger.error(
            "Telegram message failed: chat_id=%s error=%s",
            send_attempt.chat_id,
            error_text,
        )
        return {"ok": False, "message_id": 0, "error": "Chat write forbidden"}
    if isinstance(exc, RPCError):
        logger.error(
            "Telegram RPC error: chat_id=%s error=%s",
            send_attempt.chat_id,
            error_text,
            exc_info=True,
        )
        return {"ok": False, "message_id": 0, "error": error_text}
    if isinstance(exc, ValueError | TypeError):
        logger.error(
            "Invalid Telegram message parameters: chat_id=%s error=%s",
            send_attempt.chat_id,
            error_text,
            exc_info=True,
        )
        return {"ok": False, "message_id": 0, "error": error_text}
    if isinstance(exc, TimeoutError | OSError | ConnectionError):
        logger.warning(
            "Network error sending Telegram message: chat_id=%s error=%s",
            send_attempt.chat_id,
            error_text,
            exc_info=True,
        )
    else:
        logger.error(
            "Unexpected error sending Telegram message: chat_id=%s error=%s",
            send_attempt.chat_id,
            error_text,
            exc_info=True,
        )
    return await _retry_or_fail(send_attempt, 2**send_attempt.attempt, error_text)


async def _retry_or_fail(
    send_attempt: SendAttempt,
    delay_seconds: int,
    error_text: str,
) -> dict[str, Any]:
    if send_attempt.attempt >= send_attempt.max_retries:
        logger.error(
            "Telegram send exhausted retries: chat_id=%s error=%s",
            send_attempt.chat_id,
            error_text,
        )
        return {"ok": False, "message_id": 0, "error": error_text}
    await asyncio.sleep(delay_seconds)
    return await send_with_retries(
        SendAttempt(
            client=send_attempt.client,
            chat_id=send_attempt.chat_id,
            text=send_attempt.text,
            attempt=send_attempt.attempt + 1,
            max_retries=send_attempt.max_retries,
        )
    )
