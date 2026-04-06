from __future__ import annotations

from core.orchestra_thread.active_context import read_active_context
from core.orchestra_thread.mcp_tools_common import JSON_MAP, normalize_optional_str

_STRING_SCHEMA = tuple({"type": "string"}.items())


def string_schema() -> JSON_MAP:
    return dict(_STRING_SCHEMA)


def peer_from_thread(thread: JSON_MAP, agent_slug: str) -> str:
    participant_a = str(thread.get("participant_a_agent_slug") or "").strip()
    participant_b = str(thread.get("participant_b_agent_slug") or "").strip()
    if agent_slug == participant_a:
        return participant_b
    if agent_slug == participant_b:
        return participant_a
    raise RuntimeError(f"{agent_slug} is not a participant of thread {thread.get('thread_id')}")


def active_context() -> JSON_MAP:
    return read_active_context()


def context_thread_and_source() -> tuple[str | None, str | None]:
    context = active_context()
    return (
        normalize_optional_str(context.get("thread_id")),
        normalize_optional_str(context.get("source_agent_slug")),
    )
