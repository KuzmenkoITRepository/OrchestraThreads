"""MCP raw-log tool handlers."""

from __future__ import annotations

import json
from typing import Any, Protocol

from core.agent_log_analysis.errors import ValidationError

JSON_MAP = dict[str, Any]


class _RuntimeProtocol(Protocol):
    async def get_agent_raw_logs(self, payload: object) -> JSON_MAP: ...


async def get_agent_raw_logs(runtime: _RuntimeProtocol, arguments: JSON_MAP) -> JSON_MAP:
    """Handle exact raw-log retrieval over MCP."""
    _require_text(arguments, field_name="agent_slug")
    payload = await runtime.get_agent_raw_logs(dict(arguments))
    return _result(payload)


def _require_text(arguments: JSON_MAP, *, field_name: str) -> str:
    normalized = str(arguments.get(field_name) or "").strip()
    if normalized:
        return normalized
    raise ValidationError("VALIDATION_ERROR", f"{field_name} is required")


def _result(payload: JSON_MAP) -> JSON_MAP:
    response_text = json.dumps(payload, ensure_ascii=False)
    return {
        "structuredContent": payload,
        "content": [{"type": "text", "text": response_text}],
    }
