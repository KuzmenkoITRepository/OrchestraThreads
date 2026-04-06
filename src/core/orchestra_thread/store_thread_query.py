from __future__ import annotations

from typing import Any

import asyncpg

from core.orchestra_thread.store_base import row_to_dict

THREAD_WITH_SUMMARY_SELECT = """
    SELECT
        t.*,
        COALESCE(stats.event_count, 0) AS event_count,
        COALESCE(stats.pending_delivery_count, 0) AS pending_delivery_count,
        COALESCE(children.child_thread_count, 0) AS child_thread_count,
        last_event.event_id AS last_event_id,
        last_event.sequence_no AS last_event_sequence_no,
        last_event.event_kind AS last_event_kind,
        last_event.notification_status AS last_event_notification_status,
        last_event.from_agent_slug AS last_event_from_agent_slug,
        last_event.to_agent_slug AS last_event_to_agent_slug,
        last_event.message_text AS last_event_message_text,
        last_event.created_at AS last_event_created_at,
        last_event.pending_delivery AS last_event_pending_delivery
    FROM threads t
    LEFT JOIN LATERAL (
        SELECT
            COUNT(*) AS event_count,
            COUNT(*) FILTER (WHERE pending_delivery = TRUE) AS pending_delivery_count
        FROM thread_events
        WHERE thread_id = t.thread_id
    ) stats ON TRUE
    LEFT JOIN LATERAL (
        SELECT COUNT(*) AS child_thread_count
        FROM threads child
        WHERE child.parent_thread_id = t.thread_id
    ) children ON TRUE
    LEFT JOIN LATERAL (
        SELECT
            event_id,
            sequence_no,
            event_kind,
            notification_status,
            from_agent_slug,
            to_agent_slug,
            message_text,
            created_at,
            pending_delivery
        FROM thread_events
        WHERE thread_id = t.thread_id
        ORDER BY sequence_no DESC
        LIMIT 1
    ) last_event ON TRUE
"""


class ThreadQueryStoreMixin:
    pool: asyncpg.Pool | None

    async def get_thread(self, thread_id: str) -> dict[str, Any] | None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT *
                FROM threads
                WHERE thread_id = $1
                """,
                thread_id,
            )
        return row_to_dict(row)

    async def list_threads(self, *, active_only: bool, limit: int) -> list[dict[str, Any]]:
        assert self.pool is not None
        where_clause = " WHERE t.status NOT IN ('done', 'closed')" if active_only else ""
        sql = (
            f"{THREAD_WITH_SUMMARY_SELECT}{where_clause}"
            """
            ORDER BY
                CASE WHEN t.status IN ('done', 'closed') THEN 1 ELSE 0 END ASC,
                COALESCE(t.last_activity_at, t.updated_at, t.created_at) DESC,
                t.created_at DESC
            LIMIT $1
            """
        )
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, max(1, limit))
        return [payload for row in rows if (payload := row_to_dict(row)) is not None]

    async def list_threads_by_root(self, *, root_thread_id: str) -> list[dict[str, Any]]:
        assert self.pool is not None
        sql = (
            f"{THREAD_WITH_SUMMARY_SELECT}"
            """
            WHERE t.root_thread_id = $1
            ORDER BY CASE WHEN t.thread_id = t.root_thread_id THEN 0 ELSE 1 END, t.created_at ASC
            """
        )
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, root_thread_id)
        return [payload for row in rows if (payload := row_to_dict(row)) is not None]

    async def list_child_threads(self, *, parent_thread_id: str) -> list[dict[str, Any]]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT *
                FROM threads
                WHERE parent_thread_id = $1
                ORDER BY created_at ASC
                """,
                parent_thread_id,
            )
        return [payload for row in rows if (payload := row_to_dict(row)) is not None]

    async def list_thread_events(self, *, thread_id: str, limit: int) -> list[dict[str, Any]]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT *
                FROM thread_events
                WHERE thread_id = $1
                ORDER BY sequence_no ASC
                LIMIT $2
                """,
                thread_id,
                max(1, limit),
            )
        return [payload for row in rows if (payload := row_to_dict(row)) is not None]

    async def get_latest_thread_event(self, *, thread_id: str) -> dict[str, Any] | None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT *
                FROM thread_events
                WHERE thread_id = $1
                ORDER BY sequence_no DESC
                LIMIT 1
                """,
                thread_id,
            )
        return row_to_dict(row)
