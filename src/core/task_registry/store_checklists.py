from __future__ import annotations

from typing import Any

import asyncpg  # type: ignore[no-any-unimported]

from core.task_registry.store_base import row_to_dict  # type: ignore[reportMissingImports]


class TaskStoreChecklists:
    pool: asyncpg.Pool | None  # type: ignore[no-any-unimported]

    async def get_checklist(self, task_id: str) -> list[dict[str, Any]]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT *
                FROM task_checklist_items
                WHERE task_id = $1
                ORDER BY sort_order ASC, id ASC
                """,
                task_id,
            )
        return [payload for row in rows if (payload := row_to_dict(row)) is not None]

    async def update_checklist_item(
        self,
        item_id: str,
        checked: bool,
        checked_by: str | None,
    ) -> bool:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE task_checklist_items
                SET checked = $2,
                    checked_by = $3,
                    checked_at = CASE WHEN $2 THEN NOW() ELSE NULL END
                WHERE id = $1
                RETURNING 1
                """,
                item_id,
                checked,
                checked_by,
            )
        return row is not None
