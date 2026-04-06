"""Prompt construction helpers for SGR runtime."""

from __future__ import annotations

from typing import Any

from agents.sgr.agent_runtime.support.settings import normalize_optional_str
from core.orchestra_agents.runtime import EventDelivery


def tool_runtime_rules_text() -> str:
    rules = [
        "You are running inside an OrchestraThreads agent runtime.",
        "All outward communication must happen through OrchestraThreads MCP tools.",
        "Use thread_send for any peer-facing message.",
        "Use thread_status for in_progress, review, done, or closed updates.",
        "If the active thread state is unclear, call thread_current first.",
        "Use thread_expand only when compact state is insufficient.",
        "Use thread_guide when you need to refresh service workflow or routing rules.",
        "Plain assistant text is not delivered to the peer and is treated as discarded scratch output.",
        "For a response-required message event, do not finish the turn without emitting at least one thread_send or thread_status action.",
        "On inactive wake-ups, act proactively: send a follow-up, publish status, request review, or close when work is actually finished.",
        "Keep tool messages concise, concrete, and operational.",
        "Do not mention manifests, callback URLs, thread ids, llm_proxy, Docker, or runtime internals in peer-facing content.",
    ]
    return "\n".join(f"- {item}" for item in rules)


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


def _thread_header(
    primary_event: Any,
    thread_summary: dict[str, Any],
    peer_agent_slug: str,
) -> list[str]:
    scope = str(thread_summary.get("scope") or "unknown").strip() or "unknown"
    participant_a = (
        normalize_optional_str(thread_summary.get("participant_a_agent_slug")) or "unknown"
    )
    participant_b = (
        normalize_optional_str(thread_summary.get("participant_b_agent_slug")) or "unknown"
    )
    status = str(thread_summary.get("status") or "open").strip() or "open"
    owner = normalize_optional_str(thread_summary.get("owner_agent_slug")) or "unknown"
    return [
        "=== THREAD UPDATE ===",
        f"thread: {primary_event.thread_id} {scope} {participant_a}<->{participant_b}",
        f"state: {status}, owner={owner}, peer={peer_agent_slug}",
    ]


def _event_body(
    primary_event: Any,
    delivery: EventDelivery,
    thread_summary: dict[str, Any],
) -> list[str]:
    event_label = primary_event.event_kind
    if primary_event.event_kind == "notification" and primary_event.notification_status:
        event_label = f"notification:{primary_event.notification_status}"
    lines = [f"new: {event_label} from {primary_event.from_agent_slug or 'unknown'}"]
    ask_line = str(primary_event.message_text or "").strip()
    if primary_event.event_kind == "inactive":
        ask_line = (
            "Inactivity wake-up. Decide whether to follow up, "
            "publish status, request review, or close if the work is done."
        )
    if ask_line:
        lines.append(f"ask: {ask_line}")
    last_preview = thread_summary.get("last_event_message_preview")
    if last_preview:
        lines.append(f"last: {last_preview}")
    folded = max(0, len(delivery.events) - 1)
    if folded > 0:
        lines.append(f"note: {folded} older event(s) were folded into this wake-up.")
    return lines


def wake_up_block(
    *,
    delivery: EventDelivery,
    primary_event: Any,
    thread_summary: dict[str, Any],
    peer_agent_slug: str,
) -> str:
    lines = _thread_header(primary_event, thread_summary, peer_agent_slug)
    lines.extend(_event_body(primary_event, delivery, thread_summary))
    return "\n".join(lines)
