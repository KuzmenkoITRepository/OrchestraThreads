"""Low-level state helpers for the manual agent CLI."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeAlias

from core.orchestra_thread.client import OrchestraThreadsClient

JsonDict: TypeAlias = dict[str, Any]
JsonObjectList: TypeAlias = list[JsonDict]
ThreadPeers: TypeAlias = dict[str, str]

_SYSTEM_AGENT_SLUG = "orchestra_threads"


def require_client(client: OrchestraThreadsClient | None) -> OrchestraThreadsClient:
    """Return the started HTTP client or raise a runtime error."""
    if client is None:
        raise RuntimeError("HTTP client is not started")
    return client


def payload_items(payload: Mapping[str, object], *, key: str) -> JsonObjectList:
    """Return only dictionary items from a JSON payload list."""
    items = payload.get(key)
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def payload_thread_id(payload: Mapping[str, object]) -> str:
    """Extract the normalized thread id from a send/notify response."""
    thread = payload.get("thread")
    if not isinstance(thread, dict):
        return ""
    return str(thread.get("thread_id") or "").strip()


def known_peer_for_thread(
    thread_id: str | None,
    thread_peers: Mapping[str, str],
) -> str | None:
    """Resolve the remembered peer for a known thread."""
    if not thread_id:
        return None
    return thread_peers.get(thread_id)


def peer_from_event(
    event: Mapping[str, object],
    *,
    agent_slug: str,
    thread_peers: Mapping[str, str],
) -> str | None:
    """Infer the remote peer slug from an event payload."""
    from_agent_slug = str(event.get("from_agent_slug") or "").strip()
    if _is_remote_peer(from_agent_slug, agent_slug):
        return from_agent_slug

    to_agent_slug = str(event.get("to_agent_slug") or "").strip()
    if _is_remote_peer(to_agent_slug, agent_slug):
        return to_agent_slug

    thread_id = str(event.get("thread_id") or "").strip()
    return thread_peers.get(thread_id) if thread_id else None


def thread_peer(thread: Mapping[str, object], *, agent_slug: str) -> str:
    """Return the opposite participant for a thread listing row."""
    participant_a = str(thread.get("participant_a_agent_slug") or "").strip()
    participant_b = str(thread.get("participant_b_agent_slug") or "").strip()
    return participant_b if participant_a == agent_slug else participant_a


def _is_remote_peer(candidate: str, agent_slug: str) -> bool:
    return bool(candidate and candidate not in {agent_slug, _SYSTEM_AGENT_SLUG})
