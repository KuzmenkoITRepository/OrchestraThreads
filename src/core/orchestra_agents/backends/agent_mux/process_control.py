from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.orchestra_agents.backends.agent_mux import (
    backend_control,
    backend_process,
    backend_prompt,
)
from core.orchestra_agents.backends.agent_mux.backend_types import (
    AgentMuxRunRequest,
    AgentTurnContext,
)
from core.orchestra_agents.backends.agent_mux.internal import active_context_file
from core.orchestra_agents.backends.agent_mux.internal.queue_mutations import QueueEntry

logger = logging.getLogger(__name__)


class ActiveContextManager:
    def __init__(self, owner: Any) -> None:
        self._owner = owner

    def write_active_context(self, payload: dict[str, Any]) -> None:
        active_context_file.write_active_context(
            self._owner.runtime_state.active_context_path, payload
        )

    def clear_active_context(self) -> None:
        active_context_file.clear_active_context(self._owner.runtime_state.active_context_path)

    def active_context_payload(self, event: Any) -> dict[str, Any]:
        return backend_prompt.active_context_payload(
            event, context_id=self._owner.current_context_id
        )

    def active_event_matches_filters(
        self,
        active_event_payload: dict[str, Any] | None,
        *,
        thread_id: str | None,
        parent_thread_id: str | None,
    ) -> bool:
        return active_context_file.process_matches_filters(
            active_event_payload,
            thread_id=thread_id,
            parent_thread_id=parent_thread_id,
        )


class ProcessController:
    def __init__(self, owner: Any) -> None:
        self._owner = owner

    async def interrupt_active_dispatch(self, *, reason: str) -> None:
        async with self._owner._task_lock:
            process = self._owner._active_process
            dispatch_id = self._owner._active_dispatch_id
        if process is None or process.returncode is not None:
            return
        logger.info("interrupting active dispatch %s: %s", dispatch_id or "unknown", reason)
        process.terminate()

    async def clear_processor_task(self) -> None:
        async with self._owner._task_lock:
            current = self._owner._processor_task
            if current is asyncio.current_task():
                self._owner._processor_task = None

    async def set_active_dispatch(self, dispatch_id: str, payload: dict[str, Any]) -> None:
        async with self._owner._task_lock:
            self._owner._active_dispatch_id = dispatch_id
            self._owner._active_event_payload = payload

    async def clear_active_dispatch_state(self) -> None:
        async with self._owner._task_lock:
            self._owner._active_dispatch_id = None
            self._owner._active_event_payload = None
            self._owner._active_process = None

    async def schedule_processor(
        self,
        *,
        processor: Callable[[], Coroutine[Any, Any, None]],
    ) -> None:
        async with self._owner._task_lock:
            task = self._owner._processor_task
            if task is not None and not task.done():
                return
            self._owner._processor_task = asyncio.create_task(
                processor(),
                name=f"{self._owner.agent_slug}-event-processor",
            )

    async def cancel_runtime(self) -> None:
        async with self._owner._task_lock:
            process = self._owner._active_process
            processor_task = self._owner._processor_task
        if process is not None and process.returncode is None:
            process.terminate()
        if processor_task is not None:
            processor_task.cancel()
            try:
                await processor_task
            except asyncio.CancelledError:
                return


@dataclass(frozen=True)
class EngineCallbacks:
    on_processing_event: Callable[[Any], None]
    on_running_dispatch: Callable[[str], None]
    on_failed_dispatch: Callable[[str], None]
    on_completed_dispatch: Callable[..., None]


class BackendRuntimeEngine:
    def __init__(
        self,
        owner: Any,
        context_manager: ActiveContextManager,
        process_controller: ProcessController,
        callbacks: EngineCallbacks,
    ) -> None:
        self._owner = owner
        self._context_manager = context_manager
        self._process_controller = process_controller
        self._callbacks = callbacks

    async def process_queue(self) -> None:
        await backend_control.process_queue(
            claim_next_entry=self._owner.runtime_state.claim_next_entry,
            complete_entry=self._owner.runtime_state.complete_entry,
            discard_entry=lambda entry, error_text: self._owner.runtime_state.discard_entry(
                entry,
                error_text=error_text,
            ),
            requeue_entry=lambda entry, error_text: self._owner.runtime_state.requeue_entry(
                entry,
                error_text=error_text,
            ),
            clear_processor_task=self._process_controller.clear_processor_task,
            max_attempts=self._owner.settings.max_attempts,
            process_entry=self.process_queue_entry,
        )

    async def process_queue_entry(self, entry: QueueEntry) -> None:
        await backend_control.process_queue_entry(
            backend_control.QueueProcessingContext(
                entry=entry,
                runtime_state=self._owner.runtime_state,
                current_context_id=self._owner.current_context_id,
                agent_slug=self._owner.agent_slug,
                max_attempts=self._owner.settings.max_attempts,
                require_tool_call_for_response=self._owner.settings.require_tool_call_for_response,
                context_memory_entries=self._owner.settings.context_memory_entries,
                hooks=self.queue_processing_hooks(),
            )
        )

    async def run_agent_mux(
        self,
        *,
        event: Any,
        dispatch_id: str,
        artifact_dir: Path,
    ) -> dict[str, Any]:
        prompt = backend_prompt.build_dispatch_prompt(
            event=event,
            context_id=self._owner.current_context_id,
            runtime_state=self._owner.runtime_state,
        )
        run_state = await backend_process.run_agent_mux(
            AgentMuxRunRequest(
                event=event,
                dispatch_id=dispatch_id,
                artifact_dir=artifact_dir,
                working_dir=self._owner.working_dir,
                agent_slug=self._owner.agent_slug,
                context_id=self._owner.current_context_id,
                system_prompt=self._owner.system_prompt,
                settings=self._owner.settings,
                prompt=prompt,
                active_context_path=str(self._owner.runtime_state.active_context_path),
            )
        )
        process = run_state["process"]
        async with self._owner._task_lock:
            self._owner._active_process = process
        return await backend_process.collect_agent_mux_result(
            process,
            run_state["stdin_payload"],
            close_stdin_after_start=bool(run_state["close_stdin_after_start"]),
        )

    def remember_incoming_context(self, event: Any) -> None:
        backend_prompt.remember_incoming_context(
            AgentTurnContext(
                runtime_state=self._owner.runtime_state,
                context_id=self._owner.current_context_id,
                event=event,
                max_entries=self._owner.settings.context_memory_entries,
            )
        )

    def queue_processing_hooks(self) -> backend_control.QueueProcessingHooks:
        return backend_control.QueueProcessingHooks(
            on_processing_event=self._callbacks.on_processing_event,
            on_running_dispatch=self._callbacks.on_running_dispatch,
            on_failed_dispatch=self._callbacks.on_failed_dispatch,
            on_completed_dispatch=self._callbacks.on_completed_dispatch,
            remember_incoming_context=self.remember_incoming_context,
            remember_agent_output=backend_prompt.remember_agent_output,
            active_context_payload=self._context_manager.active_context_payload,
            run_agent_mux=self.run_agent_mux,
            write_active_context=self._context_manager.write_active_context,
            clear_active_context=self._context_manager.clear_active_context,
            set_active_dispatch=self._process_controller.set_active_dispatch,
            clear_active_dispatch_state=self._process_controller.clear_active_dispatch_state,
        )

    def _queue_processing_hooks(self) -> backend_control.QueueProcessingHooks:
        return self.queue_processing_hooks()
