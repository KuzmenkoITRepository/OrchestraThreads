from __future__ import annotations

from typing import Any

from core.orchestra_thread.mcp_thread_routing import compact_route, resolve_send_routing
from core.orchestra_thread.mcp_tools_common import (
    JSON_MAP,
    ensure_text,
    normalize_optional_str,
    result,
)


def _thread_send_result(payload: JSON_MAP, route: str, resolved_target: str) -> JSON_MAP:
    thread = payload.get("thread") or {}
    created_thread = bool(payload.get("created_thread"))
    return {
        "ok": True,
        "operation": "thread_send",
        "route": compact_route(route, created_thread),
        "thread_id": thread.get("thread_id"),
        "root_thread_id": thread.get("root_thread_id"),
        "parent_thread_id": thread.get("parent_thread_id"),
        "status": thread.get("status"),
        "peer_agent_slug": resolved_target,
        "created_thread": created_thread,
    }


async def thread_send(server: Any, arguments: JSON_MAP) -> JSON_MAP:
    message = ensure_text(arguments.get("message"), field_name="message")
    routing = resolve_send_routing(
        target_agent_slug=normalize_optional_str(arguments.get("target_agent_slug")),
        mode=str(arguments.get("mode") or "auto"),
        explicit_thread_id=normalize_optional_str(arguments.get("thread_id")),
    )
    payload = await server.client.send_message(
        from_agent_slug=server.agent_slug,
        to_agent_slug=routing[2],
        message_text=message,
        thread_id=routing[0],
        parent_thread_id=routing[1],
        client_request_id=normalize_optional_str(arguments.get("client_request_id")),
    )
    return result(_thread_send_result(payload, routing[3], routing[2]))
