from __future__ import annotations

from typing import Any

from agents.sgr.agent_runtime.llm_response_helpers import (
    ToolCallList,
    message_payload,
    optional_str,
    tool_calls,
)
from agents.sgr.agent_runtime.llm_stream_parser import stream_payload as _stream_payload


def completion_parts(
    payload: dict[str, Any],
) -> tuple[str | None, str, ToolCallList]:
    model = optional_str(payload.get("model"))
    message = message_payload(payload)
    if not message:
        return model, "", []
    text = optional_str(message.get("content")) or ""
    return model, text, tool_calls(message)


def stream_payload(lines: list[str]) -> dict[str, Any]:
    return _stream_payload(lines)
