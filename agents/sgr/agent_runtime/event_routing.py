"""SGR event routing — dedup, context resolution, result building."""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

from agents.sgr.agent_runtime import event_loop as _loop
from agents.sgr.agent_runtime import event_support as _event_support
from agents.sgr.agent_runtime import result_builders as _results
from agents.sgr.agent_runtime import support as _support
from core.orchestra_agents import runtime as _rt

if TYPE_CHECKING:
    from agents.sgr.agent_runtime.backend import SGRMinimaxBackend

_MAX_HANDLED_EVENTS = 512
logger = logging.getLogger(__name__)


async def handle_events(
    backend: SGRMinimaxBackend,
    delivery: _rt.EventDelivery,
) -> _rt.EventDeliveryResult:
    """Route an event delivery through dedup, context, and turn execution."""
    backend.remember_delivery(delivery)
    actionable = [ev for ev in delivery.events if _is_actionable(ev, backend.settings)]
    if not actionable:
        return _results.no_action_result(backend, delivery)
    pending = _event_support.pending_actionable_events(
        backend.handled_event_ids,
        actionable,
        _event_identity,
    )
    if not pending:
        event = actionable[-1]
        return _results.duplicate_result(backend, delivery, event, _event_identity(event))
    return await _process_events(backend, delivery, pending)


async def _process_events(
    backend: SGRMinimaxBackend,
    delivery: _rt.EventDelivery,
    pending: list[tuple[Any, str]],
) -> _rt.EventDeliveryResult:
    aggregate = _support.AgentTurnOutcome()
    state = _event_support.ProcessedEventsState()
    remaining = list(pending)
    while remaining:
        await _process_next_event(backend, delivery, aggregate, state, remaining)
    return _event_support.build_aggregate_result(
        backend,
        delivery=delivery,
        outcome=aggregate,
        state=state,
    )


async def _process_next_event(
    backend: SGRMinimaxBackend,
    delivery: _rt.EventDelivery,
    aggregate: _support.AgentTurnOutcome,
    state: _event_support.ProcessedEventsState,
    remaining: list[tuple[Any, str]],
) -> None:
    event, event_id = remaining.pop(0)
    state.last_event = event
    state.last_peer = await _process_event(backend, delivery, event, event_id, aggregate)
    state.processed_event_ids.append(event_id)


async def _process_event(
    backend: SGRMinimaxBackend,
    delivery: _rt.EventDelivery,
    event: Any,
    event_id: str,
    delivery_outcome: _support.AgentTurnOutcome,
) -> str:
    thread_summary, peer = await _resolve_context(backend, event)
    logger.info("Processing SGR event %s (%s)", event_id, event.event_kind)
    outcome = await _loop.run_turn(backend, delivery, event, thread_summary, peer)
    if event.thread_id and event.requires_response and not outcome.action_emitted:
        outcome.no_action_warning = True
        logger.warning(
            "SGR turn completed without an action for response-required event %s",
            event_id,
        )
    outcome.event_metadata = _support.extract_event_metadata(event.raw_payload)
    _event_support.record_outcome(
        backend,
        event,
        event_id,
        peer,
        outcome,
    )
    _event_support.merge_outcomes(target=delivery_outcome, source=outcome)
    return peer


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
    peer = _event_support.peer_agent_slug(
        own_slug=backend.agent_slug,
        thread_summary=thread_summary,
        event=event,
    )
    return thread_summary, peer


def _is_actionable(event: Any, settings: _support.SGRRuntimeSettings) -> bool:
    if event.event_kind == "message":
        return bool(event.requires_response)
    if event.event_kind == "notification":
        return bool(_support.normalize_optional_str(event.notification_status))
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
