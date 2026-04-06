"""Event delivery result builders for the SGR backend."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.orchestra_agents import runtime as _rt

from agents.sgr.agent_runtime import support as _support

if TYPE_CHECKING:
    from agents.sgr.agent_runtime.backend import SGRMinimaxBackend

_MAX_TOOL_ACTION_LOG = 16


def no_action_result(
    backend: SGRMinimaxBackend,
    delivery: _rt.EventDelivery,
) -> _rt.EventDeliveryResult:
    backend._status.delivery_duplicate = False
    backend._status.action_emitted = False
    backend._status.tool_actions = []
    backend._status.ignored_output_preview = None
    return _rt.EventDeliveryResult(
        accepted=True,
        accepted_events=len(delivery.events),
        delivery_id=delivery.delivery_id,
        details={
            "backend_type": backend.backend_type,
            "skipped": len(delivery.events),
            "reason": "no_actionable_events",
        },
    )


def duplicate_result(
    backend: SGRMinimaxBackend,
    delivery: _rt.EventDelivery,
    event: Any,
    event_id: str,
) -> _rt.EventDeliveryResult:
    backend._status.delivery_duplicate = True
    backend._status.action_emitted = False
    return _rt.EventDeliveryResult(
        accepted=True,
        accepted_events=len(delivery.events),
        delivery_id=delivery.delivery_id,
        duplicate=True,
        details={
            "backend_type": backend.backend_type,
            "thread_id": event.thread_id,
            "event_id": event_id,
        },
    )


def success_result(
    delivery: _rt.EventDelivery,
    outcome: _support.AgentTurnOutcome,
    details_base: dict[str, Any],
) -> _rt.EventDeliveryResult:
    details = {
        **details_base,
        "action_emitted": outcome.action_emitted,
        "llm_turns": outcome.llm_turns,
        "tool_calls": outcome.tool_calls,
        "messages_sent": outcome.messages_sent,
        "statuses_published": outcome.statuses_published,
        "used_tools": list(outcome.used_tools[-_MAX_TOOL_ACTION_LOG:]),
        "direct_text_ignored": outcome.direct_text_ignored,
    }
    if outcome.last_published_status:
        details["published_status"] = outcome.last_published_status
    if not outcome.action_emitted:
        details["reason"] = "no_tool_action_emitted"
    return _rt.EventDeliveryResult(
        accepted=True,
        accepted_events=len(delivery.events),
        delivery_id=delivery.delivery_id,
        details=details,
    )
