from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def _preview_text(text_value: Any, *, limit: int | None = None) -> str:
    preview = " ".join(str(text_value or "").split())
    if limit is None:
        return preview
    return preview[:limit]


def _memory_label(memory_entry: Mapping[str, Any]) -> str:
    base_role = str(memory_entry.get("role") or "note").strip() or "note"
    parts = [base_role]
    source = str(memory_entry.get("source_agent_slug") or "").strip()
    if source:
        parts.append(source)
    event_kind = str(memory_entry.get("event_kind") or "").strip()
    if event_kind:
        parts.append(event_kind)
    return ":".join(parts)


def _render_memory_entry(memory_entry: Mapping[str, Any]) -> str:
    label = _memory_label(memory_entry)
    preview = _preview_text(memory_entry.get("text_preview"), limit=220)
    metadata_summary = _preview_text(memory_entry.get("metadata_summary"))
    if not metadata_summary:
        return f"- {label}: {preview}"
    metadata_fragment = metadata_summary[:120]
    return f"- {label}: {preview} [{metadata_fragment}]".strip()


def build_context_memory_block(
    *, context_id: str, entries: Sequence[Mapping[str, Any]] | None = None
) -> str:
    normalized_context_id = str(context_id or "").strip() or "unknown"
    recent_entries = [
        dict(entry_item) for entry_item in (entries or []) if isinstance(entry_item, Mapping)
    ]
    lines = [
        "=== AGENT CONTEXT ===",
        f"context_id: {normalized_context_id}",
    ]
    if not recent_entries:
        lines.append("memory: empty (new or recently cleared context)")
        return "\n".join(lines)
    lines.append("recent_memory:")
    for memory_entry in recent_entries[-8:]:
        lines.append(_render_memory_entry(memory_entry))
    return "\n".join(lines)
