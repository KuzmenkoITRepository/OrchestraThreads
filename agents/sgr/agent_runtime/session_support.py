"""Session key extraction from event metadata."""

from __future__ import annotations

from typing import Any


def extract_session_key(event: Any) -> str:
    """Extract a session key from event metadata for context grouping."""
    thread_id = _optional_str(getattr(event, "thread_id", None))
    if thread_id:
        return thread_id
    chat_id = _extract_metadata_field(event, "chat_id")
    if chat_id:
        return f"chat:{chat_id}"
    from_slug = _optional_str(getattr(event, "from_agent_slug", None))
    if from_slug:
        return f"from:{from_slug}"
    return "default"


def extract_peer_slug(event: Any) -> str:
    """Extract peer agent slug from event metadata."""
    sender = _extract_metadata_field(event, "sender_name")
    if sender:
        return sender
    from_slug = _optional_str(getattr(event, "from_agent_slug", None))
    if from_slug:
        return from_slug
    return "unknown"


def _extract_metadata_field(event: Any, field: str) -> str | None:
    """Extract a field from event metadata or top-level raw_payload."""
    raw_payload = getattr(event, "raw_payload", None) or {}
    metadata = raw_payload.get("metadata") or {}
    if isinstance(metadata, dict):
        found = _optional_str(metadata.get(field))
        if found:
            return found
    return _optional_str(raw_payload.get(field))


def _optional_str(value: object) -> str | None:
    """Normalize value to optional stripped string."""
    text = str(value or "").strip()
    return text or None
