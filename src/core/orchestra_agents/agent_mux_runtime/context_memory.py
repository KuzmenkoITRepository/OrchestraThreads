from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def _preview_text(value: Any, *, limit: int | None = None) -> str:
    preview = " ".join(str(value or "").split())
    if limit is None:
        return preview
    return preview[:limit]


def _memory_label(item: Mapping[str, Any]) -> str:
    base_role = str(item.get("role") or "note").strip() or "note"
    parts = [base_role]
    source = str(item.get("source_agent_slug") or "").strip()
    if source:
        parts.append(source)
    event_kind = str(item.get("event_kind") or "").strip()
    if event_kind:
        parts.append(event_kind)
    return ":".join(parts)


def _render_memory_entry(item: Mapping[str, Any]) -> str:
    label = _memory_label(item)
    preview = _preview_text(item.get("text_preview"), limit=220)
    metadata_summary = _preview_text(item.get("metadata_summary"))
    if not metadata_summary:
        return f"- {label}: {preview}"
    metadata_fragment = metadata_summary[:120]
    return f"- {label}: {preview} [{metadata_fragment}]".strip()


def build_context_memory_block(
    *, context_id: str, entries: Sequence[Mapping[str, Any]] | None = None
) -> str:
    normalized_context_id = str(context_id or "").strip() or "unknown"
    recent_entries = [dict(item) for item in (entries or []) if isinstance(item, Mapping)]
    lines = [
        "=== AGENT CONTEXT ===",
        f"context_id: {normalized_context_id}",
    ]
    if not recent_entries:
        lines.append("memory: empty (new or recently cleared context)")
        return "\n".join(lines)
    lines.append("recent_memory:")
    for item in recent_entries[-8:]:
        lines.append(_render_memory_entry(item))
    return "\n".join(lines)
