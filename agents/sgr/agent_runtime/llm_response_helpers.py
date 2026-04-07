from __future__ import annotations

from typing import Any

ToolCallPayload = dict[str, Any]
ToolCallList = list[ToolCallPayload]


def message_payload(payload: dict[str, Any]) -> dict[str, Any]:
    choice = first_choice(payload)
    message = choice.get("message") if choice else None
    if isinstance(message, dict):
        return message
    return {}


def first_choice(payload: dict[str, Any]) -> dict[str, Any]:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return {}
    candidate = choices[0]
    if isinstance(candidate, dict):
        return candidate
    return {}


def tool_calls(message: dict[str, Any]) -> ToolCallList:
    raw_tool_calls = message.get("tool_calls")
    if not isinstance(raw_tool_calls, list):
        return []
    return [call for call in raw_tool_calls if isinstance(call, dict)]


def optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
