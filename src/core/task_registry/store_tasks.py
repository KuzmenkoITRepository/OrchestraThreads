from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

from core.task_registry.store_base import row_to_dict
from core.task_registry.store_tasks_filters import list_task_query
from core.task_registry.store_tasks_models import TaskCreateRequest


class TaskStoreTasks:
    pool: asyncpg.Pool | None

    async def create_task(self, request: TaskCreateRequest) -> dict[str, Any]:
        assert self.pool is not None
        artifacts_list = list(request.artifacts or [])
        blocked_values = [str(blocked_item) for blocked_item in request.blocked_by or []]
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
                request.title,
                request.description,
                request.status,
                request.assignee,
                request.created_by,
                request.priority,
                request.acceptance_criteria,
                request.linked_thread_id,
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

    async def list_tasks(
        self,
        *,
        status: str | None = None,
        assignee: str | None = None,
        created_by: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        assert self.pool is not None
        sql, query_params = list_task_query(
            status=status,
            assignee=assignee,
            created_by=created_by,
            limit=limit,
        )
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, *query_params)
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
