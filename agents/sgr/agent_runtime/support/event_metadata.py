from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Final

from core.orchestra_agents.agent_mux_runtime import message_preview

_SUMMARY_LIMIT: Final = 200
_SOURCE_CONTEXT_KEYS: Final = ("channel", "sender_display", "chat_title", "received_at")
STANDARD_EVENT_KEYS: Final[frozenset[str]] = frozenset(
    (
        "event_id",
        "thread_id",
        "root_thread_id",
        "parent_thread_id",
        "owner_agent_slug",
        "sequence_no",
        "event_kind",
        "notification_status",
        "from_agent_slug",
        "to_agent_slug",
        "message_text",
        "interrupts_runtime",
        "requires_response",
        "created_at",
    )
)


def extract_event_metadata(payload: Mapping[str, Any]) -> dict[str, Any]:
    extra = _extra_event_metadata(payload)
    summary = metadata_summary(payload)
    result = dict(extra)
    if summary:
        result["summary"] = summary
    return result


def metadata_summary(payload: Mapping[str, Any]) -> str | None:
    source_summary = _source_context_summary(payload.get("source_context"))
    if source_summary:
        return source_summary
    extra = _extra_event_metadata(payload)
    if not extra:
        return None
    summary = json.dumps(extra, ensure_ascii=False, sort_keys=True)
    return message_preview(summary, limit=_SUMMARY_LIMIT)


def _extra_event_metadata(payload: Mapping[str, Any]) -> dict[str, Any]:
    extra: dict[str, Any] = {}
    for key, value in payload.items():
        if str(key) not in STANDARD_EVENT_KEYS:
            extra[key] = value
    return extra


def _source_context_summary(source_context: Any) -> str | None:
    if not isinstance(source_context, Mapping) or not source_context:
        return None
    parts: list[str] = []
    for key in _SOURCE_CONTEXT_KEYS:
        value = str(source_context.get(key) or "").strip()
        if value:
            parts.append(f"{key}={value}")
    if not parts:
        return None
    return ", ".join(parts)
