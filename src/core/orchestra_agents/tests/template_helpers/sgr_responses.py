"""LLM response builders and event payload factories for SGR tests."""

from __future__ import annotations

import json
from typing import Any

from core.orchestra_agents.runtime import EventDelivery

_JsonDict = dict[str, Any]

_DEFAULT_MODEL = "MiniMax-M2.7"
_CREATED_TS = 1735689600
_PROMPT_TOKENS = 10
_COMPLETION_TOKENS = 5
_TOTAL_TOKENS = 15


def _tool_response(
    *,
    tool_name: str,
    arguments: _JsonDict,
    call_id: str,
    model: str = _DEFAULT_MODEL,
) -> _JsonDict:
    return {
        "id": f"chatcmpl-{call_id}",
        "object": "chat.completion",
        "created": _CREATED_TS,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(arguments, ensure_ascii=False),
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {
            "prompt_tokens": _PROMPT_TOKENS,
            "completion_tokens": _COMPLETION_TOKENS,
            "total_tokens": _TOTAL_TOKENS,
        },
    }


def _text_response(text: str, *, model: str = _DEFAULT_MODEL) -> _JsonDict:
    return {
        "id": "chatcmpl-text",
        "object": "chat.completion",
        "created": _CREATED_TS,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": _PROMPT_TOKENS,
            "completion_tokens": _COMPLETION_TOKENS,
            "total_tokens": _TOTAL_TOKENS,
        },
    }


def _base_event_payload() -> _JsonDict:
    return {
        "event_id": "event-1",
        "thread_id": "thread-1",
        "root_thread_id": "thread-1",
        "parent_thread_id": None,
        "owner_agent_slug": "secretary",
        "sequence_no": 3,
        "event_kind": "message",
        "notification_status": None,
        "from_agent_slug": "secretary",
        "to_agent_slug": "sgr",
        "message_text": "Please prepare the summary.",
        "interrupts_runtime": True,
        "requires_response": True,
        "created_at": "2026-04-03T07:00:00Z",
    }


def _build_delivery(*, delivery_id: str, event_payload: _JsonDict) -> EventDelivery:
    return EventDelivery.from_dict(
        {
            "delivery_id": delivery_id,
            "events": [event_payload],
        }
    )


def _inactive_status_tool_response() -> _JsonDict:
    return _tool_response(
        tool_name="thread_status",
        arguments={
            "status": "in_progress",
            "message": "Still working on the requested summary.",
            "client_request_id": "tool-status-1",
        },
        call_id="call-status",
    )
