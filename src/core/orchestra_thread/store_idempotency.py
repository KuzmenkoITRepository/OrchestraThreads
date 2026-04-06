from __future__ import annotations

import json
from typing import Any

import asyncpg


class IdempotencyStoreMixin:
    pool: asyncpg.Pool | None

    async def get_idempotent_result(
        self,
        *,
        from_agent_slug: str,
        client_request_id: str,
    ) -> dict[str, Any] | None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT response_json
                FROM idempotency_keys
                WHERE from_agent_slug = $1 AND client_request_id = $2
                """,
                from_agent_slug,
                client_request_id,
            )
        if row is None:
            return None
        payload = row["response_json"]
        if isinstance(payload, str):
            parsed_payload = json.loads(payload)
            return dict(parsed_payload) if isinstance(parsed_payload, dict) else None
        return dict(payload) if isinstance(payload, dict) else None

    async def save_idempotent_result(
        self,
        *,
        from_agent_slug: str,
        client_request_id: str,
        operation_name: str,
        response_payload: dict[str, Any],
    ) -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO idempotency_keys (
                    from_agent_slug,
                    client_request_id,
                    operation_name,
                    response_json,
                    created_at
                ) VALUES ($1, $2, $3, $4, NOW())
                ON CONFLICT (from_agent_slug, client_request_id) DO NOTHING
                """,
                from_agent_slug,
                client_request_id,
                operation_name,
                response_payload,
            )
