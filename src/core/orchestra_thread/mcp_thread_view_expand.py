from __future__ import annotations

from typing import Any

from core.orchestra_thread.mcp_thread_context import resolve_thread_id
from core.orchestra_thread.mcp_tools_common import JSON_MAP, result

DEFAULT_EXPAND_LIMIT = 5
MAX_EXPAND_LIMIT = 200


def _normalize_view(view: Any) -> str:
    normalized_view = str(view or "latest").strip().lower() or "latest"
    if normalized_view not in {"latest", "tail", "related", "full"}:
        raise RuntimeError("view must be one of latest, tail, related, full")
    return normalized_view


def _normalized_limit(limit_value: Any) -> int:
    return max(1, min(int(limit_value or DEFAULT_EXPAND_LIMIT), MAX_EXPAND_LIMIT))


def _thread_expand_result(payload: JSON_MAP, view: str, limit: int) -> JSON_MAP:
    events = payload.get("events") or []
    if view == "latest":
        return {
            "ok": True,
            "thread": payload.get("thread"),
            "latest_event": events[-1] if events else None,
        }
    if view == "tail":
        tail_count = max(1, min(limit, len(events)))
        return {
            "ok": True,
            "thread": payload.get("thread"),
            "events": events[-tail_count:],
        }
    if view == "related":
        return {
            "ok": True,
            "thread": payload.get("thread"),
            "related": payload.get("related"),
        }
    return payload


async def thread_expand(server: Any, arguments: JSON_MAP) -> JSON_MAP:
    thread_id = resolve_thread_id(arguments)
    if not thread_id:
        raise RuntimeError("thread_id is required outside an active thread")
    view = _normalize_view(arguments.get("view"))
    limit = _normalized_limit(arguments.get("limit"))
    payload = await server.client.get_thread(thread_id=thread_id, limit=limit)
    return result(_thread_expand_result(payload, view, limit))
