from __future__ import annotations

from typing import Any

import asyncpg

from core.orchestra_thread.store_base import row_to_dict


class AgentStoreMixin:
    pool: asyncpg.Pool | None

    @staticmethod
    def timestamp_within_lease(value: Any, *, lease_seconds: int) -> bool:
        return bool(value) and lease_seconds > 0

    async def upsert_agent(
        self,
        *,
        agent_slug: str,
        display_name: str,
        event_callback_url: str,
        stop_callback_url: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO agents (
                    agent_slug,
                    display_name,
                    event_callback_url,
                    stop_callback_url,
                    metadata_json,
                    registered_at,
                    last_seen_at
                ) VALUES ($1, $2, $3, $4, $5, NOW(), NOW())
                ON CONFLICT(agent_slug) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    event_callback_url = EXCLUDED.event_callback_url,
                    stop_callback_url = EXCLUDED.stop_callback_url,
                    metadata_json = EXCLUDED.metadata_json,
                    last_seen_at = EXCLUDED.last_seen_at
                RETURNING *
                """,
                agent_slug,
                display_name,
                event_callback_url,
                stop_callback_url,
                metadata,
            )
        return row_to_dict(row) or {}

    async def touch_agent(self, *, agent_slug: str) -> dict[str, Any] | None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE agents
                SET last_seen_at = NOW()
                WHERE agent_slug = $1
                RETURNING *
                """,
                agent_slug,
            )
        return row_to_dict(row)

    async def get_agent(self, agent_slug: str) -> dict[str, Any] | None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT *
                FROM agents
                WHERE agent_slug = $1
                """,
                agent_slug,
            )
        return row_to_dict(row)

    async def list_agents(self) -> list[dict[str, Any]]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT *
                FROM agents
                ORDER BY agent_slug ASC
                """
            )
        return [payload for row in rows if (payload := row_to_dict(row)) is not None]

    async def is_agent_online(self, *, agent_slug: str, lease_seconds: int) -> bool:
        agent = await self.get_agent(agent_slug)
        if agent is None:
            return False
        return self.timestamp_within_lease(agent.get("last_seen_at"), lease_seconds=lease_seconds)
