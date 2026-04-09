"""Prompt context helpers for SGR runtime."""

from __future__ import annotations


def operational_notes_text(
    *,
    peer_agent_slug: str,
) -> str:
    """Build operational notes for the LLM system prompt."""
    if not peer_agent_slug or peer_agent_slug == "unknown":
        return ""
    return f"Current peer: {peer_agent_slug}"
