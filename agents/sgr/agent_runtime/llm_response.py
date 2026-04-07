from __future__ import annotations

from typing import Any

ToolCallPayload = dict[str, Any]
ToolCallList = list[ToolCallPayload]


def completion_parts(
    payload: dict[str, Any],
) -> tuple[str | None, str, ToolCallList]:
    model = _optional_str(payload.get("model"))
    message = _message_payload(payload)
    if not message:
        return model, "", []
    text = _optional_str(message.get("content")) or ""
    return model, text, _tool_calls(message)


def _message_payload(payload: dict[str, Any]) -> dict[str, Any]:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return {}
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return {}
    message = first_choice.get("message")
    if isinstance(message, dict):
        return message
    return {}


def _tool_calls(message: dict[str, Any]) -> ToolCallList:
    raw_tool_calls = message.get("tool_calls")
    if not isinstance(raw_tool_calls, list):
        return []
    return [call for call in raw_tool_calls if isinstance(call, dict)]


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
