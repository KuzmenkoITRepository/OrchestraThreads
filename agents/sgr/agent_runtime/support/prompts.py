"""Prompt construction helpers for SGR runtime."""

from __future__ import annotations

from typing import Any

from agents.sgr.agent_runtime.support.event_metadata import metadata_summary
from agents.sgr.agent_runtime.support.settings import normalize_optional_str
from core.orchestra_agents.runtime import EventDelivery


def tool_runtime_rules_text() -> str:
    rules = [
        "You are running inside an OrchestraThreads agent runtime.",
        "Use OrchestraThreads MCP tools for outward communication.",
        "Use thread_send for peer-facing messages.",
        "Use thread_status for in_progress, review, done, or closed updates.",
        "If the active thread state is unclear, call thread_current first.",
        "Use thread_expand only when compact state is insufficient.",
        "Use thread_guide when you need to refresh service workflow or routing rules.",
        "Plain assistant text can help you think, but it is not forwarded to the peer.",
        "For response-required message events, prefer a tool action when the peer needs an update.",
        "On inactive wake-ups, act proactively: send a follow-up, publish status, request review, or close when work is actually finished.",
        "Keep tool messages concise, concrete, and operational.",
        "Do not mention manifests, callback URLs, thread ids, llm_proxy, Docker, or runtime internals in peer-facing content.",
    ]
    return "\n".join(f"- {item}" for item in rules)


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
    event_label = _event_label(primary_event)
    lines = [f"new: {event_label} from {primary_event.from_agent_slug or 'unknown'}"]
    ask_line = _event_ask_line(primary_event)
    if ask_line:
        lines.append(f"ask: {ask_line}")
    lines.extend(_event_notes(primary_event, delivery, thread_summary))
    return lines


def _event_label(primary_event: Any) -> str:
    if primary_event.event_kind == "notification" and primary_event.notification_status:
        return f"notification:{primary_event.notification_status}"
    return str(primary_event.event_kind)


def _event_ask_line(primary_event: Any) -> str:
    if primary_event.event_kind != "inactive":
        return str(primary_event.message_text or "").strip()
    return (
        "Inactivity wake-up. Decide whether to follow up, "
        "publish status, request review, or close if the work is done."
    )


def _event_notes(
    primary_event: Any,
    delivery: EventDelivery,
    thread_summary: dict[str, Any],
) -> list[str]:
    notes: list[str] = []
    metadata_note = metadata_summary(primary_event.raw_payload)
    if metadata_note:
        notes.append(f"context: {metadata_note}")
    last_preview = thread_summary.get("last_event_message_preview")
    if last_preview:
        notes.append(f"last: {last_preview}")
    folded = max(0, len(delivery.events) - 1)
    if folded > 0:
        notes.append(f"note: {folded} older event(s) were folded into this wake-up.")
    return notes


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
