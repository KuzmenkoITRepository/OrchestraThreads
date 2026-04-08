from __future__ import annotations

from typing import Any

from core.orchestra_thread.mcp_thread_context import resolve_thread_id
from core.orchestra_thread.mcp_tools_common import (
    JSON_MAP,
    ensure_text,
    normalize_optional_str,
    result,
)
from core.orchestra_thread.mcp_tools_context import active_context, peer_from_thread


async def _resolve_target_agent_slug(server: Any, arguments: JSON_MAP, thread_id: str) -> str:
    context = active_context()
    target_agent_slug = normalize_optional_str(
        arguments.get("target_agent_slug")
    ) or normalize_optional_str(context.get("source_agent_slug"))
    if target_agent_slug:
        return target_agent_slug
    compact = await server.client.get_thread_compact(thread_id=thread_id)
    return peer_from_thread(compact.get("thread") or {}, server.agent_slug)


def _thread_status_result(
    payload: JSON_MAP,
    published_status: str,
    target_agent_slug: str,
) -> JSON_MAP:
    return {
        "ok": True,
        "operation": "thread_status",
        "thread_id": (payload.get("thread") or {}).get("thread_id"),
        "status": (payload.get("thread") or {}).get("status"),
        "published_status": published_status,
        "peer_agent_slug": target_agent_slug,
        "terminal": published_status in {"done", "closed"},
        "delivered": published_status in {"in_progress", "review"},
    }


async def thread_status(server: Any, arguments: JSON_MAP) -> JSON_MAP:
    thread_id = resolve_thread_id(arguments)
    if not thread_id:
        raise RuntimeError("thread_id is required outside an active thread")
    status = ensure_text(arguments.get("status"), field_name="status")
    lower_status = status.lower()
    target_agent_slug = await _resolve_target_agent_slug(server, arguments, thread_id)
    payload = await server.client.send_notification(
        from_agent_slug=server.agent_slug,
        to_agent_slug=target_agent_slug,
        thread_id=thread_id,
        status=status,
        message_text=ensure_text(arguments.get("message"), field_name="message"),
        client_request_id=normalize_optional_str(arguments.get("client_request_id")),
    )
    return result(_thread_status_result(payload, lower_status, target_agent_slug))


def _agent_status_result(payload: JSON_MAP) -> JSON_MAP:
    return {
        "ok": True,
        "operation": "agent_status",
        "agent_slug": payload.get("agent_slug"),
        "online": bool(payload.get("online")),
        "busy": bool(payload.get("busy")),
        "status": payload.get("status"),
        "current_thread_id": payload.get("current_thread_id"),
    }


async def agent_status(server: Any, arguments: JSON_MAP) -> JSON_MAP:
    agent_slug = ensure_text(arguments.get("agent_slug"), field_name="agent_slug")
    payload = await server.client.get_agent_status(agent_slug=agent_slug)
    return result(_agent_status_result(payload))
