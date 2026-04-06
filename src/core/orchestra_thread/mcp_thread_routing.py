from __future__ import annotations

from core.orchestra_thread.mcp_thread_routing_modes import (
    resolve_auto_route,
    resolve_child_route,
    resolve_exact_route,
    resolve_root_route,
)
from core.orchestra_thread.mcp_tools_common import ROUTE, normalize_optional_str
from core.orchestra_thread.mcp_tools_context import context_thread_and_source


def ensure_mode(mode: str) -> str:
    normalized_mode = str(mode or "auto").strip().lower() or "auto"
    if normalized_mode not in {"auto", "root", "child", "exact"}:
        raise RuntimeError("mode must be one of auto, root, child, exact")
    return normalized_mode


def resolve_send_routing(
    *,
    target_agent_slug: str | None,
    mode: str,
    explicit_thread_id: str | None,
) -> ROUTE:
    current_thread_id, source_agent_slug = context_thread_and_source()
    normalized_target = normalize_optional_str(target_agent_slug)
    normalized_mode = ensure_mode(mode)
    if normalized_mode == "exact":
        return resolve_exact_route(
            current_thread_id,
            source_agent_slug,
            normalized_target,
            explicit_thread_id,
        )
    if normalized_mode == "root":
        return resolve_root_route(normalized_target)
    if normalized_mode == "child":
        return resolve_child_route(current_thread_id, normalized_target)
    return resolve_auto_route(current_thread_id, source_agent_slug, normalized_target)


def compact_route(route: str, created_thread: bool) -> str:
    if route == "root":
        return "created_root" if created_thread else "reused_root"
    if route == "child":
        return "created_child" if created_thread else "reused_child"
    return route
