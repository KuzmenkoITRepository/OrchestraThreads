"""SGR event routing — dedup, context resolution, result building."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from agents.sgr.agent_runtime import event_loop as _loop
from agents.sgr.agent_runtime import result_builders as _results
from agents.sgr.agent_runtime import support as _support
from core.orchestra_agents import runtime as _rt

if TYPE_CHECKING:
    from agents.sgr.agent_runtime.backend import SGRMinimaxBackend

_MAX_HANDLED_EVENTS = 512
_MAX_TOOL_ACTION_LOG = 16


async def handle_events(
    backend: SGRMinimaxBackend,
    delivery: _rt.EventDelivery,
) -> _rt.EventDeliveryResult:
    """Route an event delivery through dedup, context, and turn execution."""
    backend.remember_delivery(delivery)
    actionable = [ev for ev in delivery.events if _is_actionable(ev, backend.settings)]
    if not actionable:
        return _results.no_action_result(backend, delivery)
    event = actionable[-1]
    event_id = _event_identity(event)
    if event_id in backend.handled_event_ids:
        return _results.duplicate_result(backend, delivery, event, event_id)
    return await _process_event(backend, delivery, event, event_id)


async def _process_event(
    backend: SGRMinimaxBackend,
    delivery: _rt.EventDelivery,
    event: Any,
    event_id: str,
) -> _rt.EventDeliveryResult:
    thread_summary, peer = await _resolve_context(backend, event)
    outcome = await _loop.run_turn(backend, delivery, event, thread_summary, peer)
    if event.thread_id and event.requires_response and not outcome.action_emitted:
        raise RuntimeError(
            "SGR turn completed without emitting any orchestra-thread MCP action "
            "for a response-required event"
        )
    _record_outcome(backend, event, event_id, peer, outcome)
    details_base = {
        "backend_type": backend.backend_type,
        "thread_id": event.thread_id,
        "event_id": event_id,
        "peer_agent_slug": peer,
        "llm_model": backend._llm.last_model,
    }
    return _results.success_result(delivery, outcome, details_base)


async def _resolve_context(
    backend: SGRMinimaxBackend,
    event: Any,
) -> tuple[dict[str, Any], str]:
    if not event.thread_id:
        peer = _support.normalize_optional_str(event.from_agent_slug) or "unknown"
        return {}, peer
    await backend._thread_ops.ensure_registered()
    await backend._thread_ops.refresh_guide()
    compact = await backend._thread_ops.ensure_client().get_thread_compact(
        thread_id=event.thread_id
    )
    thread_summary = compact.get("thread") or {}
    peer = _peer_agent_slug(backend, thread_summary, event)
    return thread_summary, peer


def _is_actionable(event: Any, settings: _support.SGRRuntimeSettings) -> bool:
    if event.event_kind == "message":
        return bool(event.requires_response)
    if event.event_kind == "inactive":
        return settings.react_to_inactive
    return False


def _event_identity(event: Any) -> str:
    event_id = _support.normalize_optional_str(event.event_id)
    if event_id:
        return event_id
    seq_part = None if event.sequence_no is None else str(event.sequence_no)
    parts = [
        _support.normalize_optional_str(event.thread_id),
        seq_part,
        _support.normalize_optional_str(event.event_kind),
    ]
    joined = ":".join(part for part in parts if part)
    return joined or f"delivery-{uuid.uuid4().hex}"


def _peer_agent_slug(
    backend: SGRMinimaxBackend,
    thread_summary: dict[str, Any],
    event: Any,
) -> str:
    own = backend.agent_slug
    part_a = _support.normalize_optional_str(thread_summary.get("participant_a_agent_slug"))
    part_b = _support.normalize_optional_str(thread_summary.get("participant_b_agent_slug"))
    if part_a == own and part_b:
        return part_b
    if part_b == own and part_a:
        return part_a
    fallback = _support.normalize_optional_str(event.from_agent_slug)
    if fallback and fallback != own:
        return fallback
    raise RuntimeError(f"Unable to resolve peer agent for thread {event.thread_id}")


def _record_outcome(
    backend: SGRMinimaxBackend,
    event: Any,
    event_id: str,
    peer: str,
    outcome: _support.AgentTurnOutcome,
) -> None:
    backend._status.thread_id = event.thread_id
    backend._status.peer_agent_slug = peer
    backend._status.reply_preview = outcome.last_reply_preview
    backend._status.status_preview = outcome.last_status_preview
    backend._status.published_status = outcome.last_published_status
    backend._status.ignored_output_preview = outcome.ignored_text_preview
    backend._status.action_emitted = outcome.action_emitted
    backend._status.tool_actions = list(outcome.used_tools[-_MAX_TOOL_ACTION_LOG:])
    backend._status.delivery_duplicate = False
    backend._status.llm_model = backend._llm.last_model
    if event_id not in backend.handled_event_ids:
        backend.handled_event_ids.add(event_id)
        backend.handled_event_order.append(event_id)
        if len(backend.handled_event_order) > _MAX_HANDLED_EVENTS:
            stale = backend.handled_event_order.pop(0)
            backend.handled_event_ids.discard(stale)
