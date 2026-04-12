from __future__ import annotations

from typing import Any

from core.orchestra_thread.mcp_thread_context import resolve_thread_id
from core.orchestra_thread.mcp_thread_view_peers import _allowed_peer_slugs
from core.orchestra_thread.mcp_tools_common import JSON_MAP, normalize_optional_str, result
from core.orchestra_thread.mcp_tools_context import peer_from_thread


def _thread_current_empty() -> JSON_MAP:
    return result(
        {
            "ok": True,
            "active": False,
            "thread_id": None,
            "summary": "No active thread in invocation context.",
        }
    )


def _thread_waiting_on(thread: JSON_MAP, last_event_kind: str) -> str | None:
    if last_event_kind in {"message", "inactive"}:
        return normalize_optional_str(thread.get("last_event_to_agent_slug"))
    if last_event_kind != "notification":
        return None
    notification_status = normalize_optional_str(thread.get("last_event_notification_status"))
    if notification_status == "review":
        return normalize_optional_str(thread.get("owner_agent_slug"))
    return None


def _thread_allowed_actions(agent_slug: str, thread: JSON_MAP) -> list[str]:
    status = str(thread.get("status") or "").strip().lower()
    owner = str(thread.get("owner_agent_slug") or "").strip()
    if status in {"done", "closed"}:
        return []
    if agent_slug == owner:
        return [
            "thread_send",
            "thread_status:in_progress",
            "thread_status:done",
            "thread_status:closed",
        ]
    return ["thread_send", "thread_status:in_progress", "thread_status:review"]


def _filtered_allowed_actions(
    *,
    actions: list[str],
    agents: list[JSON_MAP],
    caller: str,
    peer_slug: str | None,
) -> list[str]:
    normalized_peer = str(peer_slug or "").strip()
    if not normalized_peer:
        return actions
    allowed = _allowed_peer_slugs(agents, caller)
    if allowed and normalized_peer not in allowed:
        return []
    return actions


def _thread_summary(thread: JSON_MAP, last_event_kind: str) -> tuple[str | None, str]:
    last_event_from = normalize_optional_str(thread.get("last_event_from_agent_slug"))
    last_event_to = normalize_optional_str(thread.get("last_event_to_agent_slug"))
    preview = str(thread.get("last_event_message_preview") or "").strip()
    if last_event_kind == "message":
        return last_event_from, f"{last_event_from} asked: {preview}"
    if last_event_kind == "notification":
        notification_status = normalize_optional_str(thread.get("last_event_notification_status"))
        return (
            last_event_from,
            f"{last_event_from} sent {notification_status or 'notification'}: {preview}",
        )
    if last_event_kind == "inactive":
        return last_event_from, f"Inactivity wake-up for {last_event_to}: {preview}"
    return last_event_from, "No events yet."


def _thread_current_result(server: Any, thread: JSON_MAP) -> JSON_MAP:
    last_event_kind = normalize_optional_str(thread.get("last_event_kind")) or "none"
    last_event_from, summary = _thread_summary(thread, last_event_kind)
    return {
        "ok": True,
        "active": True,
        "thread_id": thread.get("thread_id"),
        "root_thread_id": thread.get("root_thread_id"),
        "parent_thread_id": thread.get("parent_thread_id"),
        "scope": thread.get("scope"),
        "status": thread.get("status"),
        "owner_agent_slug": thread.get("owner_agent_slug"),
        "peer_agent_slug": peer_from_thread(thread, server.agent_slug),
        "waiting_on": _thread_waiting_on(thread, last_event_kind),
        "last_event_kind": last_event_kind,
        "last_message_from": last_event_from,
        "summary": summary,
        "allowed_actions": _thread_allowed_actions(server.agent_slug, thread),
    }


async def thread_current(server: Any, arguments: JSON_MAP) -> JSON_MAP:
    thread_id = resolve_thread_id(arguments)
    if not thread_id:
        return _thread_current_empty()
    compact_payload = await server.client.get_thread_compact(thread_id=thread_id)
    current = _thread_current_result(server, compact_payload.get("thread") or {})
    agents_payload = await server.client.list_agents()
    current["allowed_actions"] = _filtered_allowed_actions(
        actions=list(current.get("allowed_actions") or []),
        agents=agents_payload.get("agents") or [],
        caller=server.agent_slug,
        peer_slug=normalize_optional_str(current.get("peer_agent_slug")),
    )
    return result(current)
