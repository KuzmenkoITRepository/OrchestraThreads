from __future__ import annotations

from typing import Any

from core.task_registry.mcp_tool_params import ERROR_KEY, OK_KEY, TASK_ID_KEY, require
from core.task_registry.mcp_tool_payloads import JsonDict, text_result
from core.task_registry.store_tasks_models import TaskCreateRequest


class TaskRegistryToolsCreateMixin:
    async def _task_create(self, arguments: JsonDict) -> JsonDict:
        title = str(require(arguments, "title"))
        created_by = str(require(arguments, "created_by"))
        artifacts = arguments.get("artifacts")
        task = await self._store.create_task(
            TaskCreateRequest(
                title=title,
                description=arguments.get("description"),
                created_by=created_by,
                status=str(arguments.get("status") or "draft"),
                assignee=arguments.get("assignee"),
                priority=str(arguments.get("priority") or "normal"),
                acceptance_criteria=arguments.get("acceptance_criteria"),
                artifacts=list(artifacts) if isinstance(artifacts, list) else None,
            )
        )
        checklist_items = arguments.get("checklist")
        if isinstance(checklist_items, list) and checklist_items:
            await self._insert_checklist_items(str(task.get("id", "")), checklist_items)
        return text_result(task)

    async def _insert_checklist_items(
        self,
        task_id: str,
        checklist_items: list[JsonDict],
    ) -> None:
        assert self._store.pool is not None
        rows = _checklist_rows(task_id, checklist_items)
        if not rows:
            return
        async with self._store.pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO task_checklist_items (task_id, label, checked, sort_order)
                VALUES ($1, $2, $3, $4)
                """,
                rows,
            )

    async def _task_get(self, arguments: JsonDict) -> JsonDict:
        task_id = str(require(arguments, TASK_ID_KEY))
        task = await self._store.get_task(task_id)
        if task is None:
            return text_result({OK_KEY: False, ERROR_KEY: f"Task not found: {task_id}"})
        return text_result(task)

    async def _task_list(self, arguments: JsonDict) -> JsonDict:
        tasks = await self._store.list_tasks(
            status=arguments.get("status"),
            assignee=arguments.get("assignee"),
            created_by=arguments.get("created_by"),
            limit=int(arguments.get("limit", 100)),
        )
        return text_result({"tasks": tasks, "count": len(tasks)})

    async def _task_add_comment(self, arguments: JsonDict) -> JsonDict:
        task_id = str(require(arguments, TASK_ID_KEY))
        author = str(require(arguments, "author"))
        body = str(require(arguments, "body"))
        artifacts = arguments.get("artifacts")
        comment = await self._store.add_comment(
            task_id=task_id,
            author=author,
            body=body,
            artifacts=list(artifacts) if isinstance(artifacts, list) else None,
        )
        return text_result(comment)

    async def _task_add_artifact(self, arguments: JsonDict) -> JsonDict:
        task_id = str(require(arguments, TASK_ID_KEY))
        artifact_payload = require(arguments, "artifact")
        if not isinstance(artifact_payload, dict):
            return text_result({OK_KEY: False, ERROR_KEY: "artifact must be an object"})
        was_added = await self._store.add_artifact(task_id, artifact_payload)
        return text_result({OK_KEY: was_added})

    async def _task_link_thread(self, arguments: JsonDict) -> JsonDict:
        task_id = str(require(arguments, TASK_ID_KEY))
        thread_id = str(require(arguments, "thread_id"))
        was_linked = await self._store.link_thread(task_id, thread_id)
        return text_result({OK_KEY: was_linked})

    _store: Any


def _checklist_rows(
    task_id: str, checklist_items: list[JsonDict]
) -> list[tuple[str, str, bool, int]]:
    rows: list[tuple[str, str, bool, int]] = []
    for sort_order, checklist_entry in enumerate(checklist_items):
        label = str(checklist_entry.get("label", ""))
        if not label:
            continue
        rows.append(
            (
                task_id,
                label,
                bool(checklist_entry.get("checked", False)),
                sort_order,
            )
        )
    return rows
