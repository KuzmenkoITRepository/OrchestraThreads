from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agents.sgr.agent_runtime import result_builders as _results
from agents.sgr.agent_runtime import support as _support
from core.orchestra_agents import runtime as _rt


@dataclass
class ProcessedEventsState:
    processed_event_ids: list[str] = field(default_factory=list)
    last_event: Any | None = None
    last_peer: str = "unknown"


def pending_actionable_events(
    handled_event_ids: set[str],
    actionable: list[Any],
    event_identity: Any,
) -> list[tuple[Any, str]]:
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
    if state.last_event is None:
        return _results.no_action_result(backend, delivery)
    details_base = {
        "backend_type": backend.backend_type,
        "thread_id": state.last_event.thread_id,
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
    metadata_summary = _support.metadata_summary(event.raw_payload)
    backend._context_memory.add_entry(
        thread_id=event.thread_id,
        entry_type=event.event_kind,
        text=event.message_text
        or outcome.last_reply_preview
        or outcome.last_status_preview
        or "event",
        metadata_summary=metadata_summary,
        event_id=event_id,
    )
    backend._status.thread_id = event.thread_id
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
    if event_id in backend.handled_event_ids:
        return
    backend.handled_event_ids.add(event_id)
    backend.handled_event_order.append(event_id)
    if len(backend.handled_event_order) > 512:
        stale = backend.handled_event_order.pop(0)
        backend.handled_event_ids.discard(stale)


def peer_agent_slug(
    *,
    own_slug: str,
    thread_summary: dict[str, Any],
    event: Any,
) -> str:
    part_a = _support.normalize_optional_str(thread_summary.get("participant_a_agent_slug"))
    part_b = _support.normalize_optional_str(thread_summary.get("participant_b_agent_slug"))
    if part_a == own_slug and part_b:
        return part_b
    if part_b == own_slug and part_a:
        return part_a
    fallback = _support.normalize_optional_str(event.from_agent_slug)
    if fallback and fallback != own_slug:
        return fallback
    return "unknown"
