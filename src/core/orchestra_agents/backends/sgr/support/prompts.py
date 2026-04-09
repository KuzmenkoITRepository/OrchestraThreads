"""Prompt construction helpers for SGR runtime."""

from __future__ import annotations

from typing import Any

from core.orchestra_agents.backends.sgr.support.event_metadata import metadata_summary
from core.orchestra_agents.backends.sgr.support.settings import normalize_optional_str
from core.orchestra_agents.runtime import EventDelivery


def tool_runtime_rules_text() -> str:
    """Build the system rules message for the SGR agent runtime."""
    rules = [
        "You are running inside an event-driven agent runtime.",
        "Use the MCP tools available in this session for outward communication.",
        "Plain assistant text helps you think, but it is not forwarded externally.",
        "If you need to send a message, use a send tool explicitly.",
        "Keep tool messages concise, concrete, and operational.",
        "Do not mention manifests, callback URLs, Docker, or runtime internals.",
    ]
    return "\n".join(f"- {item}" for item in rules)


def wake_up_block(
    *,
    delivery: EventDelivery,
    primary_event: Any,
    peer_agent_slug: str,
) -> str:
    """Build the user-facing wake-up message for an event."""
    lines = _event_header(primary_event, peer_agent_slug)
    lines.extend(_event_body(primary_event, delivery))
    return "\n".join(lines)


def _event_header(
    primary_event: Any,
    peer_agent_slug: str,
) -> list[str]:
    """Build the event header block."""
    event_kind = str(primary_event.event_kind or "unknown")
    from_slug = normalize_optional_str(primary_event.from_agent_slug) or "unknown"
    return [
        "=== EVENT ===",
        f"kind: {event_kind}",
        f"from: {from_slug}, peer: {peer_agent_slug}",
    ]


def _event_body(
    primary_event: Any,
    delivery: EventDelivery,
) -> list[str]:
    """Build the event body lines."""
    lines: list[str] = []
    message_text = str(primary_event.message_text or "").strip()
    if message_text:
        lines.append(f"message: {message_text}")
    meta_note = metadata_summary(primary_event.raw_payload)
    if meta_note:
        lines.append(f"context: {meta_note}")
    folded = max(0, len(delivery.events) - 1)
    if folded > 0:
        lines.append(f"note: {folded} older event(s) were folded into this wake-up.")
    return lines
