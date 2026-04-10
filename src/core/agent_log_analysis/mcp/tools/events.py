"""MCP event-query tool handlers."""

from __future__ import annotations

import json
from typing import Any, Protocol

from core.agent_log_analysis.errors import ValidationError

JSON_MAP = dict[str, Any]


class _RuntimeProtocol(Protocol):
    async def get_event(self, event_id: str) -> JSON_MAP: ...

    async def query_agent_events(self, payload: object) -> JSON_MAP: ...


async def get_event(runtime: _RuntimeProtocol, arguments: JSON_MAP) -> JSON_MAP:
    """Handle exact event lookup over MCP."""
    payload = await runtime.get_event(_require_text(arguments, field_name="event_id"))
    return _result(payload)


async def query_agent_events(runtime: _RuntimeProtocol, arguments: JSON_MAP) -> JSON_MAP:
    """Handle bounded agent-scoped event queries over MCP."""
    payload = await runtime.query_agent_events(dict(arguments))
    return _result(payload)


async def handle_tools_call(
    runtime: _RuntimeProtocol,
    *,
    name: str,
    arguments: JSON_MAP,
) -> JSON_MAP:
    """Dispatch one MCP event tool call."""
    if name == "get_event":
        return await get_event(runtime, arguments)
    if name == "query_agent_events":
        return await query_agent_events(runtime, arguments)
    raise RuntimeError(f"Unknown tool: {name}")


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
