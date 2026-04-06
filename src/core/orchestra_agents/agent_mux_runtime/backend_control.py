from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from core.orchestra_agents.agent_mux_runtime.backend_dispatch_result import (
    record_dispatch_result,
)
from core.orchestra_agents.agent_mux_runtime.queue_processor import _QueueProcessor
from core.orchestra_agents.runtime import EventDelivery


class DispatchCompletionHook(Protocol):
    def __call__(
        self,
        status: str,
        tool_calls: list[str],
        reason: str | None,
        preview: str | None,
    ) -> None: ...


class RunAgentMuxHook(Protocol):
    async def __call__(
        self,
        *,
        event: Any,
        dispatch_id: str,
        artifact_dir: Any,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class QueueProcessingHooks:
    on_processing_event: Callable[[Any], None]
    on_running_dispatch: Callable[[str], None]
    on_failed_dispatch: Callable[[str], None]
    on_completed_dispatch: DispatchCompletionHook
    remember_incoming_context: Callable[[Any], None]
    remember_agent_output: Callable[[Any, Mapping[str, Any]], None]
    active_context_payload: Callable[[Any], dict[str, Any]]
    run_agent_mux: RunAgentMuxHook
    write_active_context: Callable[[dict[str, Any]], None]
    clear_active_context: Callable[[], None]
    set_active_dispatch: Callable[[str, dict[str, Any]], Awaitable[None]]
    clear_active_dispatch_state: Callable[[], Awaitable[None]]


@dataclass(frozen=True)
class QueueProcessingContext:
    entry: Any
    runtime_state: Any
    current_context_id: str
    agent_slug: str
    max_attempts: int
    require_tool_call_for_response: bool
    context_memory_entries: int
    hooks: QueueProcessingHooks


@dataclass(frozen=True)
class QueueProcessorConfig:
    claim_next_entry: Callable[[], Any | None]
    complete_entry: Callable[[Any], None]
    discard_entry: Callable[[Any, str], None]
    requeue_entry: Callable[[Any, str], None]
    clear_processor_task: Callable[[], Awaitable[None]]
    max_attempts: int
    process_entry: Callable[[Any], Awaitable[None]]


async def process_queue(**kwargs: Any) -> None:
    config = QueueProcessorConfig(**kwargs)
    processor = _QueueProcessor(config)
    try:
        await processor.run_queue()
    except BaseException:
        await config.clear_processor_task()
        raise
    await config.clear_processor_task()


async def process_queue_entry(context: QueueProcessingContext) -> None:
    payload = context.entry.payload
    event_payload = payload.get("payload")
    if not isinstance(event_payload, dict):
        raise RuntimeError("queue entry is missing payload")
    event = EventDelivery.from_dict(
        {"delivery_id": payload.get("delivery_id"), "events": [event_payload]}
    ).events[0]
    context.hooks.on_processing_event(event)
    context.hooks.remember_incoming_context(event)
    if not (event.requires_response or event.interrupts_runtime):
        return
    dispatch_id = uuid.uuid4().hex
    artifact_dir = context.runtime_state.artifact_dir_for_dispatch(dispatch_id)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    context.hooks.on_running_dispatch(dispatch_id)
    context.runtime_state.remember_active_dispatch(
        dispatch_id=dispatch_id,
        event_id=event.event_id,
        event_kind=event.event_kind,
        artifact_dir=str(artifact_dir),
        queue_id=context.entry.queue_id,
    )
    context.hooks.write_active_context(context.hooks.active_context_payload(event))
    await context.hooks.set_active_dispatch(dispatch_id, dict(event.raw_payload))
    await _QueueProcessor().run_dispatch(
        context,
        event,
        dispatch_id,
        artifact_dir,
        record_dispatch_result,
    )
