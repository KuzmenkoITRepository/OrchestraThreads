from __future__ import annotations

from typing import Any

from core.orchestra_agents.backends.sgr.llm_response_helpers import (
    ToolCallPayload,
    optional_str,
)


def merge_tool_calls(
    existing_calls: dict[int, ToolCallPayload],
    raw_tool_calls: Any,
) -> None:
    if not isinstance(raw_tool_calls, list):
        return
    for raw_call in raw_tool_calls:
        if not isinstance(raw_call, dict):
            continue
        index = _call_index(raw_call, existing_calls)
        current = existing_calls.setdefault(index, _empty_tool_call())
        _merge_tool_call(current, raw_call)


def _call_index(
    raw_call: dict[str, Any],
    existing_calls: dict[int, ToolCallPayload],
) -> int:
    index = raw_call.get("index")
    if isinstance(index, int):
        return index
    return len(existing_calls)


def _empty_tool_call() -> ToolCallPayload:
    return {
        "id": None,
        "type": "function",
        "function": {"name": None, "arguments": ""},
    }


def _merge_tool_call(
    current: ToolCallPayload,
    raw_call: ToolCallPayload,
) -> None:
    _merge_top_level(current, raw_call)
    function_payload = raw_call.get("function")
    if not isinstance(function_payload, dict):
        return
    _merge_function_payload(current, function_payload)


def _merge_top_level(
    current: ToolCallPayload,
    raw_call: ToolCallPayload,
) -> None:
    raw_id = optional_str(raw_call.get("id"))
    if raw_id:
        current["id"] = raw_id
    raw_type = optional_str(raw_call.get("type"))
    if raw_type:
        current["type"] = raw_type


def _merge_function_payload(
    current: ToolCallPayload,
    function_payload: dict[str, Any],
) -> None:
    current_function = current.setdefault("function", {})
    raw_name = optional_str(function_payload.get("name"))
    if raw_name:
        current_function["name"] = raw_name
    raw_arguments = function_payload.get("arguments")
    if isinstance(raw_arguments, str):
        current_function["arguments"] = str(current_function.get("arguments") or "") + raw_arguments
