from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg

from core.orchestra_thread.store_base import parse_timestamp, row_to_dict

MAX_RETRY_EXPONENT = 10


def _rowcount_from_status(status_text: str) -> int:
    parts = str(status_text or "").split()
    if not parts:
        return 0
    try:
        return int(parts[-1])
    except ValueError:
        return 0


class DeliveryStoreMixin:
    pool: asyncpg.Pool | None

    async def list_due_pending_events(self, *, now_iso: str, limit: int) -> list[dict[str, Any]]:
        assert self.pool is not None
        now = parse_timestamp(now_iso) or datetime.now(UTC)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    e.*,
                    t.root_thread_id,
                    t.parent_thread_id,
                    t.owner_agent_slug,
                    t.status AS thread_status,
                    a.event_callback_url,
                    a.last_seen_at AS agent_last_seen_at,
                    a.stop_callback_url
                FROM thread_events e
                JOIN threads t ON t.thread_id = e.thread_id
                LEFT JOIN agents a ON a.agent_slug = e.to_agent_slug
                WHERE e.pending_delivery = TRUE
                  AND t.status NOT IN ('done', 'closed')
                  AND COALESCE(e.next_delivery_attempt_at, e.created_at) <= $1
                ORDER BY COALESCE(e.next_delivery_attempt_at, e.created_at) ASC, e.created_at ASC, e.sequence_no ASC
                LIMIT $2
                """,
                now,
                max(1, limit),
            )
        return [payload for row in rows if (payload := row_to_dict(row)) is not None]

    async def mark_event_delivered(self, *, event_id: str) -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE thread_events
                SET pending_delivery = FALSE,
                    delivered_at = NOW(),
                    next_delivery_attempt_at = NULL,
                    last_delivery_error = NULL
                WHERE event_id = $1
                """,
                event_id,
            )

    async def mark_event_failed(
        self,
        *,
        event_id: str,
        error_text: str,
        retry_base_seconds: int,
        retry_max_seconds: int,
    ) -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    SELECT delivery_attempt_count
                    FROM thread_events
                    WHERE event_id = $1
                    FOR UPDATE
                    """,
                    event_id,
                )
                if row is None:
                    return
                next_attempt_count = int(row["delivery_attempt_count"] or 0) + 1
                retry_seconds = self._retry_delay_seconds(
                    attempt_count=next_attempt_count,
                    retry_base_seconds=retry_base_seconds,
                    retry_max_seconds=retry_max_seconds,
                )
                next_time = datetime.now(UTC) + timedelta(seconds=retry_seconds)
                await conn.execute(
                    """
                    UPDATE thread_events
                    SET delivery_attempt_count = $1,
                        next_delivery_attempt_at = $2,
                        last_delivery_error = $3
                    WHERE event_id = $4
                    """,
                    next_attempt_count,
                    next_time,
                    error_text[:4000],
                    event_id,
                )

    async def cancel_pending_events_for_thread(self, *, thread_id: str, reason: str) -> int:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            status_text = await conn.execute(
                """
                UPDATE thread_events
                SET pending_delivery = FALSE,
                    next_delivery_attempt_at = NULL,
                    last_delivery_error = COALESCE(last_delivery_error, $1)
                WHERE thread_id = $2 AND pending_delivery = TRUE
                """,
                reason[:4000],
                thread_id,
            )
        return _rowcount_from_status(status_text)

    def _retry_delay_seconds(
        self,
        *,
        attempt_count: int,
        retry_base_seconds: int,
        retry_max_seconds: int,
    ) -> int:
        exponent = min(attempt_count - 1, MAX_RETRY_EXPONENT)
        result = min(retry_max_seconds, retry_base_seconds * (2**exponent))
        return int(result)
