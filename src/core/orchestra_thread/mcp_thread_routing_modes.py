from __future__ import annotations

from core.orchestra_thread.mcp_tools_common import ROUTE


def resolve_exact_route(
    current_thread_id: str | None,
    source_agent_slug: str | None,
    normalized_target: str | None,
    explicit_thread_id: str | None,
) -> ROUTE:
    thread_id = explicit_thread_id or current_thread_id
    if not thread_id:
        raise RuntimeError("thread_id is required for mode=exact")
    resolved_target = normalized_target or source_agent_slug
    if not resolved_target:
        raise RuntimeError("target_agent_slug is required when no active peer is known")
    return thread_id, None, resolved_target, "exact_thread"


def resolve_root_route(normalized_target: str | None) -> tuple[None, None, str, str]:
    if not normalized_target:
        raise RuntimeError("target_agent_slug is required for mode=root")
    return None, None, normalized_target, "root"


def resolve_child_route(
    current_thread_id: str | None,
    normalized_target: str | None,
) -> tuple[None, str, str, str]:
    if not current_thread_id:
        raise RuntimeError("mode=child requires an active thread context")
    if not normalized_target:
        raise RuntimeError("target_agent_slug is required for mode=child")
    return None, current_thread_id, normalized_target, "child"


def _resolve_auto_route_in_thread(
    current_thread_id: str,
    source_agent_slug: str | None,
    normalized_target: str | None,
) -> ROUTE:
    if not normalized_target and source_agent_slug:
        return current_thread_id, None, source_agent_slug, "reply_current"
    if normalized_target and source_agent_slug and normalized_target == source_agent_slug:
        return current_thread_id, None, normalized_target, "reply_current"
    if normalized_target:
        return None, current_thread_id, normalized_target, "child"
    raise RuntimeError("target_agent_slug is required when auto routing has no known source peer")


def resolve_auto_route(
    current_thread_id: str | None,
    source_agent_slug: str | None,
    normalized_target: str | None,
) -> ROUTE:
    if current_thread_id:
        return _resolve_auto_route_in_thread(
            current_thread_id, source_agent_slug, normalized_target
        )
    if not normalized_target:
        raise RuntimeError("target_agent_slug is required outside an active thread")
    return None, None, normalized_target, "root"
