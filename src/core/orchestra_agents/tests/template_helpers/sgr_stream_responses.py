"""Streaming LLM response builders for SGR tests."""

from __future__ import annotations

import json
from typing import Any

_JsonDict = dict[str, Any]

_STREAM_MODEL = "gpt-5.4-mini-2026-03-17"
_CREATED_TS = 1735689600
_ARG_CHUNK_SIZE = 8


def _stream_tool_response(
    *,
    tool_name: str,
    arguments: _JsonDict,
    call_id: str,
    model: str = _STREAM_MODEL,
) -> list[_JsonDict]:
    serialized_args = json.dumps(arguments, ensure_ascii=False)
    chunks = [serialized_args[pos : pos + _ARG_CHUNK_SIZE] for pos in _offsets(serialized_args)]
    header = _stream_tool_header(call_id=call_id, tool_name=tool_name, model=model)
    body = [_stream_tool_arg_chunk(raw_chunk, model=model) for raw_chunk in chunks]
    return [header, *body, _stream_tool_finish(model=model)]


def _offsets(serialized: str) -> range:
    return range(0, len(serialized), _ARG_CHUNK_SIZE)


def _stream_tool_header(
    *,
    call_id: str,
    tool_name: str,
    model: str,
) -> _JsonDict:
    return {
        "id": "chatcmpl-stream-tool",
        "object": "chat.completion.chunk",
        "created": _CREATED_TS,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": call_id,
                            "type": "function",
                            "function": {"name": tool_name, "arguments": ""},
                        }
                    ]
                },
                "finish_reason": None,
            }
        ],
    }


def _stream_tool_arg_chunk(raw_chunk: str, *, model: str) -> _JsonDict:
    return {
        "id": "chatcmpl-stream-tool",
        "object": "chat.completion.chunk",
        "created": _CREATED_TS,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {"tool_calls": [{"index": 0, "function": {"arguments": raw_chunk}}]},
                "finish_reason": None,
            }
        ],
    }


def _stream_tool_finish(*, model: str) -> _JsonDict:
    return {
        "id": "chatcmpl-stream-tool",
        "object": "chat.completion.chunk",
        "created": _CREATED_TS,
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
    }
