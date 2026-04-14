"""SGR event routing — dedup, context resolution, result building."""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

from core.orchestra_agents import runtime as _rt
from core.orchestra_agents.backends.sgr import event_loop as _loop
from core.orchestra_agents.backends.sgr import event_support as _event_support
from core.orchestra_agents.backends.sgr import result_builders as _results
from core.orchestra_agents.backends.sgr import session_support as _session
from core.orchestra_agents.backends.sgr import support as _support
from core.orchestra_agents.backends.sgr.active_context_support import event_active_context_scope

if TYPE_CHECKING:
    from core.orchestra_agents.backends.sgr.backend import SGRMinimaxBackend

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
    """Process all pending events and build an aggregate result."""
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
    """Pop and process the next event from the remaining queue."""
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
    """Execute a single event through the LLM turn loop."""
    peer = _session.extract_peer_slug(event)
    session_key = _session.extract_session_key(event)
    logger.info("Processing SGR event %s (%s)", event_id, event.event_kind)
    with event_active_context_scope(backend, delivery, event):
        outcome = await _loop.run_turn(backend, delivery, event, session_key, peer)
    _apply_post_turn(outcome, event, event_id)
    _event_support.record_outcome(backend, event, event_id, peer, outcome)
    _event_support.merge_outcomes(target=delivery_outcome, source=outcome)
    return peer


def _apply_post_turn(outcome: _support.AgentTurnOutcome, event: Any, event_id: str) -> None:
    """Apply post-turn checks and metadata."""
    if event.requires_response and not outcome.action_emitted:
        outcome.no_action_warning = True
        logger.warning("SGR turn without action for event %s", event_id)
    outcome.event_metadata = _support.extract_event_metadata(event.raw_payload)


def _is_actionable(event: Any, settings: _support.SGRRuntimeSettings) -> bool:
    """Check if an event should be processed. Default: actionable."""
    if event.event_kind == "message" and not event.requires_response:
        return False
    if event.event_kind == "inactive" and not settings.react_to_inactive:
        return False
    return True


def _event_identity(event: Any) -> str:
    """Compute a dedup identity string for an event."""
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
