from __future__ import annotations

import logging

from core.task_registry.mcp.tool_params import ERROR_KEY, OK_KEY, MissingParam
from core.task_registry.mcp.tool_payloads import JsonDict, text_result
from core.task_registry.mcp.tools_create import TaskRegistryToolsCreateMixin
from core.task_registry.mcp.tools_update import TaskRegistryToolsUpdateMixin
from core.task_registry.store import TaskStore

logger = logging.getLogger(__name__)


class TaskRegistryTools(TaskRegistryToolsCreateMixin, TaskRegistryToolsUpdateMixin):
    def __init__(self, store: TaskStore) -> None:
        self._store = store

    async def dispatch(self, name: str, arguments: JsonDict) -> JsonDict:
        try:
            return await self._route(name, arguments)
        except MissingParam as exc:
            return text_result({OK_KEY: False, ERROR_KEY: str(exc)})
        except Exception as exc:
            logger.error("Tool %s failed: %s", name, exc, exc_info=True)
            return text_result({OK_KEY: False, ERROR_KEY: str(exc)})

    async def _route(self, name: str, arguments: JsonDict) -> JsonDict:
        handlers = {
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
        tool_handler = handlers.get(name)
        if tool_handler is None:
            return text_result({OK_KEY: False, ERROR_KEY: f"Unknown tool: {name}"})
        return await tool_handler(arguments)
