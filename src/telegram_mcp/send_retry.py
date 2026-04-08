"""Retry wrapper for rich sends — FloodWait and network retry parity."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from telethon.errors import ChatWriteForbiddenError, FloodWaitError

from telegram_mcp.send_pipeline import execute_send
from telegram_mcp.send_request import SendRequest

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _RichAttempt:
    """State for a single rich-send attempt."""

    client: Any
    chat_id: int
    request: SendRequest
    attempt: int
    max_retries: int
    on_flood_wait: Callable[[int], None] | None = None


async def rich_send_with_retries(
    client: Any,
    chat_id: int,
    request: SendRequest,
    *,
    max_retries: int,
    on_flood_wait: Callable[[int], None] | None = None,
) -> dict[str, Any]:
    """Execute a rich send with FloodWait and network retries."""
    attempt = _RichAttempt(
        client=client,
        chat_id=chat_id,
        request=request,
        attempt=0,
        max_retries=max_retries,
        on_flood_wait=on_flood_wait,
    )
    return await _try_rich(attempt)


async def _try_rich(attempt: _RichAttempt) -> dict[str, Any]:
    try:
        return await execute_send(attempt.client, attempt.chat_id, attempt.request)
    except ChatWriteForbiddenError:
        return {"ok": False, "message_id": 0, "error": "Chat write forbidden"}
    except FloodWaitError as exc:
        wait = max(0, int(exc.seconds))
        logger.warning("Flood wait on rich send: %ss (attempt %s)", wait, attempt.attempt + 1)
        if attempt.on_flood_wait is not None:
            attempt.on_flood_wait(wait)
        return await _retry_or_fail(attempt, wait)
    except (TimeoutError, OSError) as exc:
        logger.warning("Network error on rich send: %s", exc, exc_info=True)
        return await _retry_or_fail(attempt, 2**attempt.attempt)


async def _retry_or_fail(attempt: _RichAttempt, delay: int) -> dict[str, Any]:
    if attempt.attempt >= attempt.max_retries:
        return {"ok": False, "message_id": 0, "error": "Exhausted retries"}
    await asyncio.sleep(delay)
    next_attempt = _RichAttempt(
        client=attempt.client,
        chat_id=attempt.chat_id,
        request=attempt.request,
        attempt=attempt.attempt + 1,
        max_retries=attempt.max_retries,
        on_flood_wait=attempt.on_flood_wait,
    )
    return await _try_rich(next_attempt)
