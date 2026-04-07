from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

import asyncpg  # type: ignore[no-any-unimported]

from core.task_registry.store_base import row_to_dict  # type: ignore[reportMissingImports]


class TaskStoreTasks:
    pool: asyncpg.Pool | None  # type: ignore[no-any-unimported]

    async def create_task(  # noqa: WPS211  # create_task accepts the task fields plus optional metadata.
        self,
        title: str,
        description: str | None,
        created_by: str,
        *,
        status: str = "draft",
        assignee: str | None = None,
        priority: str = "normal",
        acceptance_criteria: str | None = None,
        linked_thread_id: UUID | str | None = None,
        blocked_by: Sequence[UUID | str] | None = None,
        artifacts: Sequence[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        assert self.pool is not None
        artifacts_list = list(artifacts or [])
        blocked_values = [str(value) for value in blocked_by or []]
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO tasks (
                    title,
                    description,
                    status,
                    assignee,
                    created_by,
                    priority,
                    acceptance_criteria,
                    linked_thread_id,
                    blocked_by,
                    artifacts
                ) VALUES (
                    $1,
                    $2,
                    $3,
                    $4,
                    $5,
                    $6,
                    $7,
                    $8::uuid,
                    COALESCE($9::uuid[], ARRAY[]::uuid[]),
                    COALESCE($10::jsonb, '[]'::jsonb)
                )
                RETURNING *
                """,
                title,
                description,
                status,
                assignee,
                created_by,
                priority,
                acceptance_criteria,
                linked_thread_id,
                blocked_values,
                artifacts_list,
            )
        return row_to_dict(row) or {}

    async def get_task(self, task_id: str) -> dict[str, Any] | None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT *
                FROM tasks
                WHERE id = $1
                """,
                task_id,
            )
        return row_to_dict(row)

    async def list_tasks(  # noqa: WPS210  # Filtering requires several local variables for SQL assembly.
        self,
        *,
        status: str | None = None,
        assignee: str | None = None,
        created_by: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        assert self.pool is not None
        conditions: list[str] = []
        params: list[object] = []
        if status is not None:
            params.append(status)
            conditions.append(f"status = ${len(params)}")
        if assignee is not None:
            params.append(assignee)
            conditions.append(f"assignee = ${len(params)}")
        if created_by is not None:
            params.append(created_by)
            conditions.append(f"created_by = ${len(params)}")
        params.append(max(1, limit))
        where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = (
            "SELECT * FROM tasks"
            f"{where_clause}"
            " ORDER BY updated_at DESC, created_at DESC"
            f" LIMIT ${len(params)}"
        )
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
        return [payload for row in rows if (payload := row_to_dict(row)) is not None]

    async def update_task_status(self, task_id: str, status: str) -> bool:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE tasks
                SET status = $2,
                    updated_at = NOW()
                WHERE id = $1
                RETURNING 1
                """,
                task_id,
                status,
            )
        return row is not None

    async def assign_task(self, task_id: str, assignee: str | None) -> bool:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE tasks
                SET assignee = $2,
                    updated_at = NOW()
                WHERE id = $1
                RETURNING 1
                """,
                task_id,
                assignee,
            )
        return row is not None

    async def link_thread(self, task_id: str, thread_id: UUID | str | None) -> bool:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE tasks
                SET linked_thread_id = $2::uuid,
                    updated_at = NOW()
                WHERE id = $1
                RETURNING 1
                """,
                task_id,
                thread_id,
            )
        return row is not None

    async def add_artifact(self, task_id: str, artifact: dict[str, Any]) -> bool:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE tasks
                SET artifacts = COALESCE(artifacts, '[]'::jsonb) || jsonb_build_array($2::jsonb),
                    updated_at = NOW()
                WHERE id = $1
                RETURNING 1
                """,
                task_id,
                artifact,
            )
        return row is not None
