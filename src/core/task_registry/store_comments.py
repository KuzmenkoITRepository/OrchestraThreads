from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import asyncpg

from core.task_registry.store_base import row_to_dict


class TaskStoreComments:
    pool: asyncpg.Pool | None

    async def add_comment(
        self,
        task_id: str,
        author: str,
        body: str,
        artifacts: Sequence[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        assert self.pool is not None
        artifact_payload = json.dumps(list(artifacts or []))
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO task_comments (
                    task_id,
                    author,
                    body,
                    artifacts
                ) VALUES (
                    $1,
                    $2,
                    $3,
                    COALESCE($4::jsonb, '[]'::jsonb)
                )
                RETURNING *
                """,
                task_id,
                author,
                body,
                artifact_payload,
            )
        return row_to_dict(row) or {}
