from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from core.orchestra_agents.agent_mux_runtime.backend_types import (
    AgentOutputContext,
    AgentTurnContext,
)
from core.orchestra_agents.agent_mux_runtime.event_metadata import (
    extra_event_metadata,
    metadata_summary,
)
from core.orchestra_agents.agent_mux_runtime.normalization import (
    message_preview,
    sanitize_reply_text,
)
from core.orchestra_agents.agent_mux_runtime.prompt_builder import (
    build_compact_wakeup_block,
    build_context_memory_block,
)


def extract_tool_calls(result: Mapping[str, Any]) -> list[str]:
    activity = result.get("activity")
    if not isinstance(activity, Mapping):
        return []
    tool_calls = activity.get("tool_calls")
    if not isinstance(tool_calls, list):
        return []
    return [str(item).strip() for item in tool_calls if str(item).strip()]


def dispatch_preview(result: Mapping[str, Any]) -> str | None:
    response = sanitize_reply_text(str(result.get("response") or ""))
    if response:
        return message_preview(response, limit=400)
    summary = sanitize_reply_text(str(result.get("handoff_summary") or ""))
    if summary:
        return message_preview(summary, limit=400)
    tool_calls = extract_tool_calls(result)
    if tool_calls:
        return f"tools: {', '.join(tool_calls[:6])}"
    return None


def build_dispatch_prompt(*, event: Any, context_id: str, runtime_state: Any) -> str:
    wakeup = build_compact_wakeup_block(event=event, folded_event_count=0)
    context_memory = build_context_memory_block(
        context_id=context_id,
        entries=runtime_state.context_snapshot().get("recent_entries") or [],
    )
    active_event_json = json.dumps(
        active_context_payload(event, context_id=context_id), ensure_ascii=False, indent=2
    )
    return "\n\n".join(
        (
            "You are handling one incoming agent event.",
            "Use configured tools or MCP servers for any external side effects.",
            "Plain assistant text is not automatically delivered to upstream systems.",
            "If the event requires a response, emit the necessary tool actions before you finish.",
            wakeup,
            context_memory,
            f"Active event payload:\n{active_event_json}",
        )
    ).strip()


def remember_incoming_context(context: AgentTurnContext) -> None:
    context.runtime_state.append_context_entry(
        context_id=context.context_id,
        role="source",
        event_id=context.event.event_id,
        event_kind=context.event.event_kind,
        source_agent_slug=context.event.from_agent_slug,
        text=context.event.message_text,
        metadata_summary=metadata_summary(context.event.raw_payload),
        max_entries=context.max_entries,
    )


def remember_agent_output(context: AgentOutputContext, result: Mapping[str, Any]) -> None:
    preview = dispatch_preview(result) or "dispatch completed"
    tool_calls = extract_tool_calls(result)
    tool_summary: str | None = f"tool_calls={', '.join(tool_calls[:6])}"
    if not tool_calls:
        tool_summary = None
    context.runtime_state.append_context_entry(
        context_id=context.context_id,
        role="agent",
        event_id=context.event.event_id,
        event_kind=context.event.event_kind,
        source_agent_slug=context.agent_slug,
        text=preview,
        metadata_summary=tool_summary,
        max_entries=context.max_entries,
    )


def active_context_payload(event: Any, *, context_id: str) -> dict[str, Any]:
    payload = {
        "context_id": context_id,
        "event_id": event.event_id,
        "event_kind": event.event_kind,
        "from_agent_slug": event.from_agent_slug,
        "to_agent_slug": event.to_agent_slug,
        "created_at": event.created_at,
        "message_text": event.message_text,
        "requires_response": bool(event.requires_response),
        "interrupts_runtime": bool(event.interrupts_runtime),
    }
    for optional_key in (
        "thread_id",
        "root_thread_id",
        "parent_thread_id",
        "owner_agent_slug",
        "notification_status",
    ):
        value = getattr(event, optional_key, None)
        if value is None:
            continue
        payload[optional_key] = value
    metadata = extra_event_metadata(event.raw_payload)
    if metadata:
        payload["metadata"] = metadata
    return payload
