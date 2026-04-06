from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import asyncpg

from core.orchestra_thread.common import normalize_participants
from core.orchestra_thread.store_base import row_to_dict

OPEN_THREADS_BY_PAIR_SQL = """
    SELECT *
    FROM threads
    WHERE parent_thread_id IS NULL
      AND participant_a_agent_slug = $1
      AND participant_b_agent_slug = $2
      AND status NOT IN ('done', 'closed')
    ORDER BY updated_at DESC, created_at DESC
    LIMIT 1
"""

OPEN_CHILD_THREADS_BY_PAIR_SQL = """
    SELECT *
    FROM threads
    WHERE parent_thread_id = $1
      AND participant_a_agent_slug = $2
      AND participant_b_agent_slug = $3
      AND status NOT IN ('done', 'closed')
    ORDER BY updated_at DESC, created_at DESC
    LIMIT 1
"""


@dataclass(frozen=True)
class RootThreadRequest:
    thread_id: str
    owner_agent_slug: str
    from_agent_slug: str
    to_agent_slug: str


@dataclass(frozen=True)
class ChildThreadRequest:
    thread_id: str
    root_thread_id: str
    parent_thread_id: str
    owner_agent_slug: str
    from_agent_slug: str
    to_agent_slug: str


class ThreadCreationStoreMixin:
    pool: asyncpg.Pool | None

    async def get_or_create_root_thread(
        self, *, request: RootThreadRequest
    ) -> tuple[dict[str, Any], bool]:
        assert self.pool is not None
        participant_a, participant_b = normalize_participants(
            request.from_agent_slug,
            request.to_agent_slug,
        )
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                existing = await conn.fetchrow(
                    OPEN_THREADS_BY_PAIR_SQL, participant_a, participant_b
                )
                if existing is not None:
                    return row_to_dict(existing) or {}, False
                created = await conn.fetchrow(
                    """
                    INSERT INTO threads (
                        thread_id,
                        root_thread_id,
                        parent_thread_id,
                        owner_agent_slug,
                        participant_a_agent_slug,
                        participant_b_agent_slug,
                        status,
                        last_sequence_no,
                        created_at,
                        updated_at
                    ) VALUES ($1, $1, NULL, $2, $3, $4, 'open', 0, NOW(), NOW())
                    ON CONFLICT DO NOTHING
                    RETURNING *
                    """,
                    request.thread_id,
                    request.owner_agent_slug,
                    participant_a,
                    participant_b,
                )
                if created is not None:
                    return row_to_dict(created) or {}, True
                return await self._find_root_by_participants(participant_a, participant_b)

    async def get_or_create_child_thread(
        self,
        *,
        request: ChildThreadRequest,
    ) -> tuple[dict[str, Any], bool]:
        assert self.pool is not None
        participant_a, participant_b = normalize_participants(
            request.from_agent_slug,
            request.to_agent_slug,
        )
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                existing = await conn.fetchrow(
                    OPEN_CHILD_THREADS_BY_PAIR_SQL,
                    request.parent_thread_id,
                    participant_a,
                    participant_b,
                )
                if existing is not None:
                    return row_to_dict(existing) or {}, False
                created = await conn.fetchrow(
                    """
                    INSERT INTO threads (
                        thread_id,
                        root_thread_id,
                        parent_thread_id,
                        owner_agent_slug,
                        participant_a_agent_slug,
                        participant_b_agent_slug,
                        status,
                        last_sequence_no,
                        created_at,
                        updated_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, 'open', 0, NOW(), NOW())
                    ON CONFLICT DO NOTHING
                    RETURNING *
                    """,
                    request.thread_id,
                    request.root_thread_id,
                    request.parent_thread_id,
                    request.owner_agent_slug,
                    participant_a,
                    participant_b,
                )
                if created is not None:
                    return row_to_dict(created) or {}, True
                return await self._find_child_by_participants(
                    request.parent_thread_id,
                    participant_a,
                    participant_b,
                )

    async def _find_root_by_participants(
        self,
        participant_a: str,
        participant_b: str,
    ) -> tuple[dict[str, Any], bool]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            existing = await conn.fetchrow(OPEN_THREADS_BY_PAIR_SQL, participant_a, participant_b)
        if existing is not None:
            return row_to_dict(existing) or {}, False
        raise RuntimeError("Thread upsert conflict without retrievable root thread")

    async def _find_child_by_participants(
        self,
        parent_thread_id: str,
        participant_a: str,
        participant_b: str,
    ) -> tuple[dict[str, Any], bool]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            existing = await conn.fetchrow(
                OPEN_CHILD_THREADS_BY_PAIR_SQL,
                parent_thread_id,
                participant_a,
                participant_b,
            )
        if existing is not None:
            return row_to_dict(existing) or {}, False
        raise RuntimeError("Thread upsert conflict without retrievable child thread")
