from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.orchestra_agents.backends.agent_mux.backend_prompt import (
    dispatch_preview,
    extract_tool_calls,
)
from core.orchestra_agents.backends.agent_mux.backend_types import AgentOutputContext


def record_dispatch_result(
    context: Any,
    event: Any,
    dispatch_id: str,
    result: Mapping[str, Any],
) -> None:
    status = dispatch_status(result)
    tool_calls = extract_tool_calls(result)
    preview = dispatch_preview(result)
    context.hooks.on_completed_dispatch(
        status,
        tool_calls,
        dispatch_reason(result),
        preview,
    )
    context.runtime_state.remember_dispatch_result(
        context_id=context.current_context_id,
        dispatch_id=dispatch_id,
        session_id=session_id(result),
        event_id=event.event_id,
        event_kind=event.event_kind,
    )
    ensure_dispatch_success(
        context,
        event,
        tool_calls,
        result,
        status,
    )
    context.hooks.remember_agent_output(
        AgentOutputContext(
            runtime_state=context.runtime_state,
            context_id=context.current_context_id,
            agent_slug=context.agent_slug,
            event=event,
            max_entries=context.context_memory_entries,
        ),
        result,
    )


def dispatch_status(result: Mapping[str, Any]) -> str:
    raw_status = str(result.get("status") or "").strip().lower()
    return raw_status or "failed"


def dispatch_reason(result: Mapping[str, Any]) -> str | None:
    reason = str(result.get("reason") or "").strip()
    return reason or None


def session_id(result: Mapping[str, Any]) -> str | None:
    metadata = result.get("metadata")
    if not isinstance(metadata, dict):
        return None
    value = str(metadata.get("session_id") or "").strip()
    return value or None


def dispatch_error(result: Mapping[str, Any]) -> str:
    reason = str(
        result.get("reason") or result.get("error") or "agent-mux execution failed"
    ).strip()
    return reason or "agent-mux execution failed"


def ensure_dispatch_success(
    context: Any,
    event: Any,
    tool_calls: list[str],
    result: Mapping[str, Any],
    status: str,
) -> None:
    if status != "completed":
        raise RuntimeError(dispatch_error(result))
    if context.require_tool_call_for_response and event.requires_response and not tool_calls:
        raise RuntimeError("dispatch completed without any tool call for a response-required event")
