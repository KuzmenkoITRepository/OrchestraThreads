from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from agents.sgr.agent_runtime.context_memory import ContextEntry


def operational_notes_text(
    guide_text: str,
    *,
    thread_summary: dict[str, Any],
    peer_agent_slug: str,
) -> str:
    notes: list[str] = []
    if guide_text:
        notes.append(guide_text)
    compact_lines = [
        "Compact thread state:",
        f"- thread_id: {thread_summary.get('thread_id') or '-'}",
        f"- root_thread_id: {thread_summary.get('root_thread_id') or '-'}",
        f"- parent_thread_id: {thread_summary.get('parent_thread_id') or '-'}",
        f"- scope: {thread_summary.get('scope') or '-'}",
        f"- status: {thread_summary.get('status') or '-'}",
        f"- owner_agent_slug: {thread_summary.get('owner_agent_slug') or '-'}",
        f"- peer_agent_slug: {peer_agent_slug or '-'}",
        f"- last_event_kind: {thread_summary.get('last_event_kind') or '-'}",
        f"- last_event_from_agent_slug: {thread_summary.get('last_event_from_agent_slug') or '-'}",
        f"- last_event_to_agent_slug: {thread_summary.get('last_event_to_agent_slug') or '-'}",
        f"- last_event_message_preview: {thread_summary.get('last_event_message_preview') or '-'}",
    ]
    notes.append("\n".join(compact_lines))
    return "\n\n".join(part for part in notes if part).strip()


def context_memory_block(entries: Sequence[ContextEntry]) -> str:
    if not entries:
        return ""
    lines = ["Recent context:"]
    for entry in entries:
        suffix = f" [{entry.metadata_summary}]" if entry.metadata_summary else ""
        lines.append(f"- {entry.entry_type}: {entry.text}{suffix}")
    return "\n".join(lines)
