"""SSE stream consumption logic."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from core.telegram_events import _sse_parser as _parser
from core.telegram_events.sse_event import SSEEvent

logger = logging.getLogger(__name__)


async def process_stream(
    response: httpx.Response,
    running: Callable[[], bool],
    on_event: Callable[[SSEEvent], Awaitable[None]] | None,
) -> None:
    """Process SSE stream until running becomes False."""
    buffer = ""
    async for chunk in response.aiter_bytes():
        if not running():
            break
        buffer += chunk.decode("utf-8")
        buffer = await process_buffer(buffer, on_event)


async def process_buffer(
    buffer: str,
    on_event: Callable[[SSEEvent], Awaitable[None]] | None,
) -> str:
    """Process SSE buffer chunks and fire events."""
    while "\n\n" in buffer:
        event_block, buffer = buffer.split("\n\n", 1)
        payload = _parser.parse_sse_block(event_block)
        if payload is not None:
            event = _build_event(payload)
            if on_event is not None:
                await on_event(event)
    return buffer


def _build_event(payload: dict[str, Any]) -> SSEEvent:
    return SSEEvent(
        event_id=payload["event_id"],
        event_type=payload["event_type"],
        occurred_at=payload["occurred_at"],
        mode=payload["mode"],
        account=payload["account"],
        update=payload["update"],
    )


async def handle_stream_error(
    current_delay: float,
    max_delay: float,
    exc: Exception,
) -> float:
    """Log error and return next retry delay."""
    logger.error(
        "SSE stream error (reconnecting in %.1fs): %s",
        current_delay,
        exc,
        exc_info=True,
    )
    await asyncio.sleep(current_delay)
    return min(current_delay * 2, max_delay)
