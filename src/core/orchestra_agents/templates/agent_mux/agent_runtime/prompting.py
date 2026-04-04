"""Compact prompt helpers for the generic agent_mux runtime."""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from core.orchestra_agents.runtime import AgentEvent


# Standard event keys that are recognized and handled specially.
# Thread-related fields (thread_id, root_thread_id, parent_thread_id, owner_agent_slug)
# are OPTIONAL metadata - they are passed through when present but not required by the runtime.
# The runtime is event-agnostic and works with any event type (threads, Telegram, calendar, etc.).
_STANDARD_EVENT_KEYS = {
    "event_id",
    "thread_id",  # optional: only present for thread-based events
    "root_thread_id",  # optional: only present for thread-based events
    "parent_thread_id",  # optional: only present for thread-based events
    "owner_agent_slug",  # optional: only present for thread-based events
    "sequence_no",
    "event_kind",
    "notification_status",
    "from_agent_slug",
    "to_agent_slug",
    "message_text",
    "interrupts_runtime",
    "requires_response",
    "created_at",
}


def _compact_json(value: Any, *, limit: int = 400) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)]}..."


def build_compact_wakeup_block(
    *,
    event: AgentEvent,
    folded_event_count: int = 0,
) -> str:
    """Render a short wake-up block suitable for a generic worker dispatch."""

    lines = [
        "=== EVENT UPDATE ===",
        f"event_id: {event.event_id or 'unknown'}",
        f"kind: {event.event_kind}",
        f"requires_response: {'yes' if event.requires_response else 'no'}",
        f"interrupts_runtime: {'yes' if event.interrupts_runtime else 'no'}",
    ]
    if event.created_at:
        lines.append(f"created_at: {event.created_at}")
    if event.from_agent_slug or event.to_agent_slug:
        lines.append(
            f"route: {event.from_agent_slug or 'unknown'} -> {event.to_agent_slug or 'unknown'}"
        )
    message = " ".join(str(event.message_text or "").split())
    if message:
        lines.append(f"message: {message}")

    source_context = event.raw_payload.get("source_context")
    if isinstance(source_context, Mapping) and source_context:
        lines.append(
            f"source_context: {_compact_json(dict(source_context), limit=500)}"
        )

    extra_metadata = {
        str(key): value
        for key, value in event.raw_payload.items()
        if str(key) not in _STANDARD_EVENT_KEYS and key != "source_context"
    }
    if extra_metadata:
        lines.append(f"metadata: {_compact_json(extra_metadata, limit=500)}")

    if folded_event_count > 0:
        lines.append(f"note: {folded_event_count} older event(s) folded.")
    return "\n".join(lines)


def build_context_memory_block(
    *, context_id: str, entries: Sequence[Mapping[str, Any]] | None = None
) -> str:
    normalized_context_id = str(context_id or "").strip() or "unknown"
    recent_entries = [
        dict(item) for item in (entries or []) if isinstance(item, Mapping)
    ]
    lines = [
        "=== AGENT CONTEXT ===",
        f"context_id: {normalized_context_id}",
    ]
    if not recent_entries:
        lines.append("memory: empty (new or recently cleared context)")
        return "\n".join(lines)
    lines.append("recent_memory:")
    for item in recent_entries[-8:]:
        role = str(item.get("role") or "note").strip() or "note"
        source = str(item.get("source_agent_slug") or "").strip()
        event_kind = str(item.get("event_kind") or "").strip()
        preview = " ".join(str(item.get("text_preview") or "").split())
        metadata_summary = " ".join(str(item.get("metadata_summary") or "").split())
        label = role
        if source:
            label = f"{label}:{source}"
        if event_kind:
            label = f"{label}:{event_kind}"
        rendered = preview[:220]
        if metadata_summary:
            rendered = f"{rendered} [{metadata_summary[:120]}]".strip()
        lines.append(f"- {label}: {rendered}")
    return "\n".join(lines)
