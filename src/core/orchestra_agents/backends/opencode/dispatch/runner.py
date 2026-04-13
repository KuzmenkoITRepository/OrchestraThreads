from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from aiohttp import ClientError

from core.orchestra_agents.backends.opencode.backend_context import (
    clear_file,
    write_active_context,
)
from core.orchestra_agents.backends.opencode.runtime.state import (
    DedupState,
    DispatchState,
)
from core.orchestra_agents.runtime.contracts import AgentEvent

if TYPE_CHECKING:
    from core.orchestra_agents.backends.opencode.runtime.backend_impl import (
        OpencodeOmoBackend,
    )

_LOGGER = logging.getLogger(__name__)


def classify_events(
    events: list[AgentEvent],
    dedup: DedupState,
) -> tuple[list[AgentEvent], int, list[str]]:
    dispatchable: list[AgentEvent] = []
    duplicate_count = 0
    queued_ids: list[str] = []
    for event in events:
        event_id = str(event.event_id or "").strip() or None
        if event_id and dedup.contains(event_id):
            duplicate_count += 1
            continue
        if event_id:
            dedup.remember(event_id)
            queued_ids.append(event_id)
        dispatchable.append(event)
    return dispatchable, duplicate_count, queued_ids


def dispatch_matches(
    state: DispatchState,
    thread_id: str | None,
    parent_thread_id: str | None,
) -> bool:
    event = state.event
    if event is None:
        return False
    if thread_id and event.thread_id == thread_id:
        return True
    return bool(parent_thread_id and event.parent_thread_id == parent_thread_id)


async def cancel_dispatch(state: DispatchState) -> None:
    task = state.task
    if task is None:
        return
    state.task = None
    state.event = None
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        return


def fire_dispatch(backend: OpencodeOmoBackend, event: AgentEvent) -> None:
    task = asyncio.create_task(run_dispatch(backend, event))
    backend._dispatch.task = task
    backend._dispatch.event = event
    task.add_done_callback(lambda completed: _on_dispatch_done(completed, backend._dispatch))


async def run_dispatch(backend: OpencodeOmoBackend, event: AgentEvent) -> None:
    if backend._components.dispatcher is None:
        return
    async with backend._dispatch.lock:
        write_active_context(
            backend._paths.active_context,
            event,
            backend.context.current_id,
            backend.agent_slug,
        )
        try:
            await _dispatch_once(backend, event)
        except Exception:
            clear_file(backend._paths.active_context)
            raise
        clear_file(backend._paths.active_context)


def _on_dispatch_done(done_task: asyncio.Task[None], state: DispatchState) -> None:
    if done_task.cancelled():
        return
    try:
        done_task.result()
    except (RuntimeError, OSError, ClientError) as exc:
        _LOGGER.exception("opencode dispatch failed", exc_info=exc)
    if state.task is done_task:
        state.task = None
        state.event = None


async def _dispatch_once(backend: OpencodeOmoBackend, event: AgentEvent) -> None:
    result = await backend._components.dispatcher.dispatch_event(
        event,
        backend.context.current_id,
        timeout=backend._dispatch_timeout,
    )
    backend._dispatch.last_result = dict(result)
