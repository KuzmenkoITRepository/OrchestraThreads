from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg

from core.orchestra_thread.store_base import row_to_dict


class NotificationStoreMixin:
    pool: asyncpg.Pool | None

    async def update_thread_terminal_status(
        self,
        *,
        thread_id: str,
        status: str,
    ) -> dict[str, Any] | None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE threads
                SET status = $1,
                    terminal_at = COALESCE(terminal_at, NOW()),
                    updated_at = NOW()
                WHERE thread_id = $2 AND status NOT IN ('done', 'closed')
                RETURNING *
                """,
                status,
                thread_id,
            )
        if row is not None:
            return row_to_dict(row)
        return await self.get_thread(thread_id)

    async def list_inactivity_candidates(
        self,
        *,
        timeout_seconds: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        assert self.pool is not None
        cutoff = datetime.now(UTC) - timedelta(seconds=timeout_seconds)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT *
                FROM threads
                WHERE status NOT IN ('done', 'closed')
                  AND last_message_sender_agent_slug IS NOT NULL
                  AND last_activity_at IS NOT NULL
                  AND last_activity_at <= $1
                  AND (
                        last_inactivity_event_at IS NULL
                        OR last_inactivity_event_at <= $1
                  )
                ORDER BY last_activity_at ASC
                LIMIT $2
                """,
                cutoff,
                max(1, limit),
            )
        return [payload for row in rows if (payload := row_to_dict(row)) is not None]

    async def mark_inactivity_sent(self, *, thread_id: str) -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE threads
                SET last_inactivity_event_at = NOW(), updated_at = NOW()
                WHERE thread_id = $1
                """,
                thread_id,
            )

    async def get_thread(self, thread_id: str) -> dict[str, Any] | None: ...
