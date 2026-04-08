from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Final

from core.orchestra_agents.agent_mux_runtime.normalization import message_preview

METADATA_SUMMARY_LIMIT = 200
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


def extra_event_metadata(payload: Mapping[str, Any]) -> dict[str, Any]:
    extra: dict[str, Any] = {}
    for metadata_key, metadata_value in payload.items():
        normalized_key = str(metadata_key)
        if normalized_key in STANDARD_EVENT_KEYS:
            continue
        extra[normalized_key] = metadata_value
    return extra


def metadata_summary(payload: Mapping[str, Any]) -> str | None:
    source_summary = _source_context_summary(payload.get("source_context"))
    if source_summary:
        return source_summary
    extra = extra_event_metadata(payload)
    if not extra:
        return None
    summary = json.dumps(extra, ensure_ascii=False, sort_keys=True)
    return message_preview(summary, limit=METADATA_SUMMARY_LIMIT)


def _source_context_summary(source_context: Any) -> str | None:
    if not isinstance(source_context, Mapping) or not source_context:
        return None
    parts = [
        f"{key}={context_value}"
        for key in ("channel", "sender_display", "chat_title", "received_at")
        if (context_value := str(source_context.get(key) or "").strip())
    ]
    if not parts:
        return None
    return ", ".join(parts)
