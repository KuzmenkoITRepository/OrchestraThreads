"""MCP timeline and correlation tool handlers."""

from __future__ import annotations

import json
from typing import Any, Protocol

from core.agent_log_analysis.errors import ValidationError

JSON_MAP = dict[str, Any]


class _RuntimeProtocol(Protocol):
    async def get_agent_timeline(self, payload: object) -> JSON_MAP: ...

    async def get_agent_correlation_chain(self, payload: object) -> JSON_MAP: ...


async def get_agent_timeline(runtime: _RuntimeProtocol, arguments: JSON_MAP) -> JSON_MAP:
    """Handle bounded agent timeline queries over MCP."""
    _require_text(arguments, field_name="agent_slug")
    payload = await runtime.get_agent_timeline(dict(arguments))
    return _result(payload)


async def get_agent_correlation_chain(
    runtime: _RuntimeProtocol,
    arguments: JSON_MAP,
) -> JSON_MAP:
    """Handle bounded agent correlation chain queries over MCP."""
    _require_text(arguments, field_name="agent_slug")
    _require_text(arguments, field_name="correlation_id")
    payload = await runtime.get_agent_correlation_chain(dict(arguments))
    return _result(payload)


async def handle_tools_call(
    runtime: _RuntimeProtocol,
    *,
    name: str,
    arguments: JSON_MAP,
) -> JSON_MAP:
    """Dispatch one MCP timeline/correlation tool call."""
    if name == "get_agent_timeline":
        return await get_agent_timeline(runtime, arguments)
    if name == "get_agent_correlation_chain":
        return await get_agent_correlation_chain(runtime, arguments)
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
