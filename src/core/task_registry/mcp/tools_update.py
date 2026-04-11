from __future__ import annotations

from typing import Any

from core.task_registry.mcp.tool_params import OK_KEY, TASK_ID_KEY, require
from core.task_registry.mcp.tool_payloads import JsonDict, text_result


class TaskRegistryToolsUpdateMixin:
    async def _task_update_status(self, arguments: JsonDict) -> JsonDict:
        task_id = str(require(arguments, TASK_ID_KEY))
        status = str(require(arguments, "status"))
        was_updated = await self._store.update_task_status(task_id, status)
        return text_result({OK_KEY: was_updated})

    async def _task_assign(self, arguments: JsonDict) -> JsonDict:
        task_id = str(require(arguments, TASK_ID_KEY))
        assignee = str(require(arguments, "assignee"))
        was_assigned = await self._store.assign_task(task_id, assignee)
        return text_result({OK_KEY: was_assigned})

    async def _task_get_checklist(self, arguments: JsonDict) -> JsonDict:
        task_id = str(require(arguments, TASK_ID_KEY))
        checklist_items = await self._store.get_checklist(task_id)
        return text_result({"items": checklist_items, "count": len(checklist_items)})

    async def _task_update_checklist(self, arguments: JsonDict) -> JsonDict:
        item_id = str(require(arguments, "item_id"))
        checked_raw = require(arguments, "checked")
        checked_by = str(require(arguments, "checked_by"))
        was_updated = await self._store.update_checklist_item(
            item_id, bool(checked_raw), checked_by
        )
        return text_result({OK_KEY: was_updated})

    _store: Any
