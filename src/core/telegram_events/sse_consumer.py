"""SSE consumer for better-telegram-mcp relay."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx

from core.telegram_events import _sse_stream as _stream

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SSEEvent:
    """Parsed SSE event from better-telegram-mcp."""

    event_id: str
    event_type: str
    occurred_at: str
    mode: str
    account: str
    update: dict[str, Any]


def _build_headers(bearer_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {bearer_token}",
        "Accept": "text/event-stream",
        "Cache-Control": "no-cache",
    }


class SSEConsumer:
    """Consumes Telegram events from better-telegram-mcp via SSE."""

    def __init__(
        self,
        events_url: str,
        bearer_token: str,
        on_event: Callable[[SSEEvent], Awaitable[None]] | None = None,
    ) -> None:
        self.events_url = events_url
        self.bearer_token = bearer_token
        self._on_event: Callable[[SSEEvent], Awaitable[None]] | None = on_event
        self._client: httpx.AsyncClient | None = None
        self._running = False

    async def start(self) -> None:
        """Start consuming SSE events."""
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=None))
        self._running = True
        logger.info("Starting SSE consumer from %s", self.events_url)
        asyncio.create_task(self._consume_loop())

    async def stop(self) -> None:
        """Stop consuming SSE events."""
        self._running = False
        if self._client:
            await self._client.aclose()
            self._client = None
        logger.info("SSE consumer stopped")

    async def _consume_loop(self) -> None:
        """Main consumption loop with reconnection logic."""
        retry_delay = 1.0
        max_retry_delay = 30.0

        while self._running:
            should_continue = await self._try_consume_or_handle_error(retry_delay, max_retry_delay)
            if should_continue is None:
                break
            retry_delay = should_continue

    async def _try_consume_or_handle_error(
        self,
        retry_delay: float,
        max_retry_delay: float,
    ) -> float | None:
        """Try one session. Return new delay on success, or None to stop."""
        try:
            await self._run_single_session()
        except asyncio.CancelledError:
            return None
        except Exception as exc:
            return await self._handle_error(retry_delay, max_retry_delay, exc)
        return _success_delay()

    async def _run_single_session(self) -> None:
        """Run one SSE connection session."""
        if self._client is None:
            msg = "SSE consumer not started"
            raise RuntimeError(msg)

        headers = _build_headers(self.bearer_token)
        async with self._client.stream("GET", self.events_url, headers=headers) as response:
            response.raise_for_status()
            logger.info("SSE connection established")
            await _stream.process_stream(response, lambda: self._running, self._on_event)

    async def _handle_error(
        self,
        retry_delay: float,
        max_retry_delay: float,
        exc: Exception,
    ) -> float | None:
        """Handle stream error and return next retry delay or None to stop."""
        if not self._running:
            return None
        logger.error(
            "SSE stream error (reconnecting in %.1fs): %s",
            retry_delay,
            exc,
            exc_info=True,
        )
        await asyncio.sleep(retry_delay)
        return min(retry_delay * 2, max_retry_delay)


def _success_delay() -> float:
    """Return default delay after successful session."""
    return 1.0
