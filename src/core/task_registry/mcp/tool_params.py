from __future__ import annotations

from typing import Any

from core.task_registry.mcp.tool_payloads import JsonDict

ERROR_KEY = "error"
OK_KEY = "ok"
TASK_ID_KEY = "task_id"


class MissingParam(Exception):
    def __init__(self, field: str) -> None:
        super().__init__(f"Missing required parameter: {field}")
        self.field = field


def require(arguments: JsonDict, field: str) -> Any:  # noqa: ANN401  # MCP arguments are untyped dicts.
    field_value = arguments.get(field)
    if field_value is None:
        raise MissingParam(field)
    return field_value
