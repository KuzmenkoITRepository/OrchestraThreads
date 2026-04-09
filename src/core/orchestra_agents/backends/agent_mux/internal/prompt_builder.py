"""Compact prompt helpers for the generic agent_mux runtime."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from core.orchestra_agents.backends.agent_mux.internal.context_memory import (
    build_context_memory_block as build_context_memory_block,
)
from core.orchestra_agents.backends.agent_mux.internal.event_metadata import STANDARD_EVENT_KEYS
from core.orchestra_agents.runtime import AgentEvent


def _compact_json(value: Any, *, limit: int = 400) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)]}..."


def _extra_metadata(event: AgentEvent) -> dict[str, Any]:
    extra: dict[str, Any] = {}
    for key, value in event.raw_payload.items():
        normalized_key = str(key)
        if normalized_key in STANDARD_EVENT_KEYS or key == "source_context":
            continue
        extra[normalized_key] = value
    return extra


def _base_wakeup_lines(event: AgentEvent) -> list[str]:
    return [
        "=== EVENT UPDATE ===",
        f"event_id: {event.event_id or 'unknown'}",
        f"kind: {event.event_kind}",
        f"requires_response: {'yes' if event.requires_response else 'no'}",
        f"interrupts_runtime: {'yes' if event.interrupts_runtime else 'no'}",
    ]


def _optional_wakeup_lines(event: AgentEvent) -> list[str]:
    lines: list[str] = []
    if event.created_at:
        lines.append(f"created_at: {event.created_at}")
    if event.from_agent_slug is not None or event.to_agent_slug is not None:
        lines.append(
            f"route: {event.from_agent_slug or 'unknown'} -> {event.to_agent_slug or 'unknown'}"
        )
    message = " ".join(str(event.message_text or "").split())
    if message:
        lines.append(f"message: {message}")
    source_context = event.raw_payload.get("source_context")
    if isinstance(source_context, Mapping) and source_context:
        lines.append(f"source_context: {_compact_json(dict(source_context), limit=500)}")
    extra_metadata = _extra_metadata(event)
    if extra_metadata:
        lines.append(f"metadata: {_compact_json(extra_metadata, limit=500)}")
    return lines


def build_compact_wakeup_block(
    *,
    event: AgentEvent,
    folded_event_count: int = 0,
) -> str:
    """Render a short wake-up block suitable for a generic worker dispatch."""

    lines = _base_wakeup_lines(event)
    lines.extend(_optional_wakeup_lines(event))

    if folded_event_count > 0:
        lines.append(f"note: {folded_event_count} older event(s) folded.")
    return "\n".join(lines)
