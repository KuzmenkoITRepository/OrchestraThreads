from __future__ import annotations

from typing import Any

from core.orchestra_memory.mcp_tools_common import (
    JSON_MAP,
    ensure_positive_int,
    ensure_text,
    normalize_optional_str,
    result,
)


def _reject_slug_override(arguments: JSON_MAP) -> None:
    override = normalize_optional_str(arguments.get("agent_slug"))
    if override is None:
        return
    raise RuntimeError("agent_slug override is not allowed")


async def memory_remember(server: Any, arguments: JSON_MAP) -> JSON_MAP:
    _reject_slug_override(arguments)
    memory = await server.client.remember(
        agent_slug=server.agent_slug,
        room=ensure_text(arguments.get("room"), field_name="room"),
        category=ensure_text(arguments.get("category"), field_name="category"),
        text=ensure_text(arguments.get("text"), field_name="text"),
    )
    return result({"ok": True, "operation": "memory_remember", "memory": memory})


async def memory_search(server: Any, arguments: JSON_MAP) -> JSON_MAP:
    _reject_slug_override(arguments)
    items = await server.client.search(
        agent_slug=server.agent_slug,
        query=str(arguments.get("query") or ""),
        room=normalize_optional_str(arguments.get("room")),
        category=normalize_optional_str(arguments.get("category")),
        limit=ensure_positive_int(arguments.get("limit"), field_name="limit", default=20),
    )
    return result(
        {
            "ok": True,
            "operation": "memory_search",
            "agent_slug": server.agent_slug,
            "count": len(items),
            "items": items,
        }
    )


async def memory_delete(server: Any, arguments: JSON_MAP) -> JSON_MAP:
    _reject_slug_override(arguments)
    deleted = await server.client.delete(
        agent_slug=server.agent_slug,
        memory_id=ensure_text(arguments.get("memory_id"), field_name="memory_id"),
    )
    return result(
        {
            "ok": deleted,
            "operation": "memory_delete",
            "agent_slug": server.agent_slug,
            "deleted": deleted,
        }
    )


async def memory_clear(server: Any, arguments: JSON_MAP) -> JSON_MAP:
    _reject_slug_override(arguments)
    deleted_count = await server.client.clear(
        agent_slug=server.agent_slug,
        room=normalize_optional_str(arguments.get("room")),
        category=normalize_optional_str(arguments.get("category")),
    )
    return result(
        {
            "ok": True,
            "operation": "memory_clear",
            "agent_slug": server.agent_slug,
            "deleted_count": deleted_count,
        }
    )
