from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from core.task_registry.store import TaskStore

logger = logging.getLogger(__name__)

JsonDict = dict[str, Any]


def _json_default(obj: Any) -> Any:
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _text_result(payload: JsonDict) -> JsonDict:
    return {
        "content": [
            {"type": "text", "text": json.dumps(payload, ensure_ascii=False, default=_json_default)}
        ]
    }


def _require(arguments: JsonDict, field: str) -> Any:  # noqa: ANN401  # MCP arguments are untyped dicts.
    value = arguments.get(field)
    if value is None:
        raise _MissingParam(field)
    return value


class _MissingParam(Exception):
    def __init__(self, field: str) -> None:
        super().__init__(f"Missing required parameter: {field}")
        self.field = field


class TaskRegistryTools:  # noqa: WPS214  # Tool dispatch needs a handler per MCP tool.
    def __init__(self, store: TaskStore) -> None:
        self._store = store

    async def dispatch(self, name: str, arguments: JsonDict) -> JsonDict:  # noqa: WPS212  # Dispatch branches are flat.
        try:
            return await self._route(name, arguments)
        except _MissingParam as exc:
            return _text_result({"ok": False, "error": str(exc)})
        except Exception as exc:
            logger.error("Tool %s failed: %s", name, exc, exc_info=True)
            return _text_result({"ok": False, "error": str(exc)})

    async def _route(  # noqa: WPS212, C901  # Single dispatch for all 10 tools needs the branches.
        self,
        name: str,
        arguments: JsonDict,
    ) -> JsonDict:
        handlers: dict[str, Any] = {
            "task_create": self._task_create,
            "task_get": self._task_get,
            "task_list": self._task_list,
            "task_update_status": self._task_update_status,
            "task_assign": self._task_assign,
            "task_add_comment": self._task_add_comment,
            "task_add_artifact": self._task_add_artifact,
            "task_link_thread": self._task_link_thread,
            "task_get_checklist": self._task_get_checklist,
            "task_update_checklist": self._task_update_checklist,
        }
        handler = handlers.get(name)
        if handler is None:
            return _text_result({"ok": False, "error": f"Unknown tool: {name}"})
        result: JsonDict = await handler(arguments)
        return result

    async def _task_create(  # noqa: WPS210  # Extracting many fields from arguments dict.
        self,
        arguments: JsonDict,
    ) -> JsonDict:
        title = str(_require(arguments, "title"))
        created_by = str(_require(arguments, "created_by"))
        task = await self._store.create_task(
            title=title,
            description=arguments.get("description"),
            created_by=created_by,
            status=str(arguments.get("status") or "draft"),
            assignee=arguments.get("assignee"),
            priority=str(arguments.get("priority") or "normal"),
            acceptance_criteria=arguments.get("acceptance_criteria"),
        )
        checklist = arguments.get("checklist")
        if isinstance(checklist, list) and checklist:
            await self._insert_checklist_items(str(task.get("id", "")), checklist)
        return _text_result(task)

    async def _insert_checklist_items(
        self,
        task_id: str,
        items: list[JsonDict],
    ) -> None:
        assert self._store.pool is not None
        async with self._store.pool.acquire() as conn:
            for idx, item in enumerate(items):
                label = str(item.get("label", ""))
                if not label:
                    continue
                checked = bool(item.get("checked", False))
                await conn.execute(  # noqa: WPS476  # Checklist inserts are sequential per item.
                    """
                    INSERT INTO task_checklist_items (task_id, label, checked, sort_order)
                    VALUES ($1, $2, $3, $4)
                    """,
                    task_id,
                    label,
                    checked,
                    idx,
                )

    async def _task_get(self, arguments: JsonDict) -> JsonDict:
        task_id = str(_require(arguments, "task_id"))
        task = await self._store.get_task(task_id)
        if task is None:
            return _text_result({"ok": False, "error": f"Task not found: {task_id}"})
        return _text_result(task)

    async def _task_list(self, arguments: JsonDict) -> JsonDict:
        tasks = await self._store.list_tasks(
            status=arguments.get("status"),
            assignee=arguments.get("assignee"),
            created_by=arguments.get("created_by"),
            limit=int(arguments.get("limit", 100)),
        )
        return _text_result({"tasks": tasks, "count": len(tasks)})

    async def _task_update_status(self, arguments: JsonDict) -> JsonDict:
        task_id = str(_require(arguments, "task_id"))
        status = str(_require(arguments, "status"))
        ok = await self._store.update_task_status(task_id, status)
        return _text_result({"ok": ok})

    async def _task_assign(self, arguments: JsonDict) -> JsonDict:
        task_id = str(_require(arguments, "task_id"))
        assignee = str(_require(arguments, "assignee"))
        ok = await self._store.assign_task(task_id, assignee)
        return _text_result({"ok": ok})

    async def _task_add_comment(self, arguments: JsonDict) -> JsonDict:
        task_id = str(_require(arguments, "task_id"))
        author = str(_require(arguments, "author"))
        body = str(_require(arguments, "body"))
        artifacts = arguments.get("artifacts")
        comment = await self._store.add_comment(
            task_id=task_id,
            author=author,
            body=body,
            artifacts=list(artifacts) if isinstance(artifacts, list) else None,
        )
        return _text_result(comment)

    async def _task_add_artifact(self, arguments: JsonDict) -> JsonDict:
        task_id = str(_require(arguments, "task_id"))
        artifact = _require(arguments, "artifact")
        if not isinstance(artifact, dict):
            return _text_result({"ok": False, "error": "artifact must be an object"})
        ok = await self._store.add_artifact(task_id, artifact)
        return _text_result({"ok": ok})

    async def _task_link_thread(self, arguments: JsonDict) -> JsonDict:
        task_id = str(_require(arguments, "task_id"))
        thread_id = str(_require(arguments, "thread_id"))
        ok = await self._store.link_thread(task_id, thread_id)
        return _text_result({"ok": ok})

    async def _task_get_checklist(self, arguments: JsonDict) -> JsonDict:
        task_id = str(_require(arguments, "task_id"))
        items = await self._store.get_checklist(task_id)
        return _text_result({"items": items, "count": len(items)})

    async def _task_update_checklist(self, arguments: JsonDict) -> JsonDict:
        item_id = str(_require(arguments, "item_id"))
        checked_raw = _require(arguments, "checked")
        checked_by = str(_require(arguments, "checked_by"))
        checked = bool(checked_raw)
        ok = await self._store.update_checklist_item(item_id, checked, checked_by)
        return _text_result({"ok": ok})
