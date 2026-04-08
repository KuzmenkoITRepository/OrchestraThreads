from __future__ import annotations

import json
from typing import Any

from agents.sgr.agent_runtime.llm_response_helpers import (
    ToolCallPayload,
    first_choice,
    optional_str,
)
from agents.sgr.agent_runtime.llm_tool_call_merge import merge_tool_calls


def stream_payload(lines: list[str]) -> dict[str, Any]:
    parsed = _StreamingResponseParser()
    for raw_line in lines:
        parsed.consume_line(raw_line)
    return parsed.payload()


class _StreamingResponseParser:
    def __init__(self) -> None:
        self._model: str | None = None
        self._content_parts: list[str] = []
        self._tool_calls: dict[int, ToolCallPayload] = {}
        self._finish_reason: str | None = None

    def consume_line(self, raw_line: str) -> None:
        payload = _event_payload(raw_line)
        if payload is None:
            return
        chunk = _parsed_chunk(payload)
        if not chunk:
            return
        self._merge_chunk(chunk)

    def payload(self) -> dict[str, Any]:
        message = _message_payload(self._content_parts)
        ordered_tool_calls = [self._tool_calls[index] for index in sorted(self._tool_calls)]
        if ordered_tool_calls:
            message["tool_calls"] = ordered_tool_calls
        return {
            "model": self._model,
            "choices": [
                {
                    "index": 0,
                    "message": message,
                    "finish_reason": _finish_reason(
                        self._finish_reason,
                        ordered_tool_calls,
                    ),
                }
            ],
        }

    def _merge_chunk(self, chunk: dict[str, Any]) -> None:
        self._model = self._model or optional_str(chunk.get("model"))
        choice = first_choice(chunk)
        if not choice:
            return
        self._finish_reason = optional_str(choice.get("finish_reason")) or self._finish_reason
        delta = choice.get("delta")
        if not isinstance(delta, dict):
            return
        self._append_content(delta)
        merge_tool_calls(self._tool_calls, delta.get("tool_calls"))

    def _append_content(self, delta: dict[str, Any]) -> None:
        content = optional_str(delta.get("content"))
        if content:
            self._content_parts.append(content)


def _event_payload(raw_line: str) -> str | None:
    if not raw_line.startswith("data:"):
        return None
    payload = raw_line[5:].strip()
    if not payload or payload == "[DONE]":
        return None
    return payload


def _parsed_chunk(raw_payload: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_payload)
    except json.JSONDecodeError:
        return {}
    if isinstance(parsed, dict):
        return parsed
    return {}


def _message_payload(content_parts: list[str]) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": "".join(content_parts) or None,
    }


def _finish_reason(
    current_finish_reason: str | None,
    ordered_tool_calls: list[ToolCallPayload],
) -> str:
    if current_finish_reason is not None:
        return current_finish_reason
    if ordered_tool_calls:
        return "tool_calls"
    return "stop"
