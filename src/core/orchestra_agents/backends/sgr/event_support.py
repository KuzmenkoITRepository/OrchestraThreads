"""Event processing support — dedup, aggregation, outcome recording."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.orchestra_agents import runtime as _rt
from core.orchestra_agents.backends.sgr import result_builders as _results
from core.orchestra_agents.backends.sgr import session_support as _session
from core.orchestra_agents.backends.sgr import support as _support


@dataclass
class ProcessedEventsState:
    """Tracks state across multiple processed events in a delivery."""

    processed_event_ids: list[str] = field(default_factory=list)
    last_event: Any | None = None
    last_peer: str = "unknown"


def pending_actionable_events(
    handled_event_ids: set[str],
    actionable: list[Any],
    event_identity: Any,
) -> list[tuple[Any, str]]:
    """Filter actionable events to those not yet handled."""
    pending: list[tuple[Any, str]] = []
    for event in actionable:
        event_id = event_identity(event)
        if event_id not in handled_event_ids:
            pending.append((event, event_id))
    return pending


def merge_outcomes(
    *,
    target: _support.AgentTurnOutcome,
    source: _support.AgentTurnOutcome,
) -> None:
    """Merge source turn outcome into target."""
    target.llm_turns += source.llm_turns
    target.tool_calls += source.tool_calls
    target.messages_sent += source.messages_sent
    target.statuses_published += source.statuses_published
    target.tool_errors += source.tool_errors
    target.used_tools.extend(source.used_tools)
    target.direct_text_ignored = target.direct_text_ignored or source.direct_text_ignored
    target.no_action_warning = target.no_action_warning or source.no_action_warning
    if source.ignored_text_preview:
        target.ignored_text_preview = source.ignored_text_preview
    if source.last_reply_preview:
        target.last_reply_preview = source.last_reply_preview
    if source.last_status_preview:
        target.last_status_preview = source.last_status_preview
    if source.last_published_status:
        target.last_published_status = source.last_published_status
    if source.event_metadata:
        target.event_metadata = dict(source.event_metadata)


def build_aggregate_result(
    backend: Any,
    delivery: _rt.EventDelivery,
    outcome: _support.AgentTurnOutcome,
    state: ProcessedEventsState,
) -> _rt.EventDeliveryResult:
    """Build aggregate delivery result from processed events."""
    if state.last_event is None:
        return _results.no_action_result(backend, delivery)
    details_base = {
        "backend_type": backend.backend_type,
        "event_id": state.processed_event_ids[-1],
        "event_ids": list(state.processed_event_ids),
        "peer_agent_slug": state.last_peer,
        "llm_model": backend._llm.last_model,
    }
    return _results.success_result(delivery, outcome, details_base)


def record_outcome(
    backend: Any,
    event: Any,
    event_id: str,
    peer: str,
    outcome: _support.AgentTurnOutcome,
) -> None:
    """Record a turn outcome into backend state."""
    session_key = _session.extract_session_key(event)
    user_text = str(event.message_text or "").strip()
    assistant_text = outcome.last_reply_preview or outcome.last_status_preview or ""
    if user_text:
        backend._chat_history.record_turn(
            session_key=session_key,
            user_text=user_text,
            assistant_text=assistant_text,
        )
    backend._status.peer_agent_slug = peer
    backend._status.reply_preview = outcome.last_reply_preview
    backend._status.status_preview = outcome.last_status_preview
    backend._status.published_status = outcome.last_published_status
    backend._status.ignored_output_preview = outcome.ignored_text_preview
    backend._status.action_emitted = outcome.action_emitted
    backend._status.tool_actions = list(outcome.used_tools[-16:])
    backend._status.total_turns += outcome.llm_turns
    backend._status.total_tool_calls += outcome.tool_calls
    backend._status.total_tool_errors += outcome.tool_errors
    backend._status.total_messages_sent += outcome.messages_sent
    backend._status.total_statuses_published += outcome.statuses_published
    backend._status.delivery_duplicate = False
    backend._status.llm_model = backend._llm.last_model
    _deduplicate_event(backend, event_id)


def _deduplicate_event(backend: Any, event_id: str) -> None:
    """Track event id for deduplication with bounded memory."""
    if event_id in backend.handled_event_ids:
        return
    backend.handled_event_ids.add(event_id)
    backend.handled_event_order.append(event_id)
    if len(backend.handled_event_order) > 512:
        stale = backend.handled_event_order.pop(0)
        backend.handled_event_ids.discard(stale)
