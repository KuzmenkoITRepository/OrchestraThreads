from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import dataclass
from typing import Any

from core.orchestra_agents.agent_mux_runtime import backend_settings, normalization
from core.orchestra_agents.runtime import (
    BaseAgentBackend,
    ClearContextRequest,
    EventDelivery,
    EventDeliveryResult,
    StopRequest,
)
from core.orchestra_agents.templates.agent_mux.agent_runtime.process_control import (
    ActiveContextManager,
    BackendRuntimeEngine,
    EngineCallbacks,
    ProcessController,
)
from core.orchestra_agents.templates.agent_mux.agent_runtime.state import AgentMuxRuntimeState
from core.orchestra_agents.templates.agent_mux.agent_runtime.status_tracking import StatusTracker


@dataclass(frozen=True)
class _LLMClientConfig:
    route_policy: str
    model: str | None
    timeout_seconds: float | None
    reasoning_effort: str | None
    reasoning_summary: str | None
    text_verbosity: str | None


class _StatusField:
    def __init__(self, field_name: str) -> None:
        self._field_name = field_name

    def __get__(self, instance: AgentMuxBackend | None, owner: type[AgentMuxBackend]) -> Any:
        if instance is None:
            return self
        if not isinstance(instance, owner):
            return self
        return getattr(instance._status, self._field_name)


def _sanitize_reply_text(text: str) -> str:
    return normalization.sanitize_reply_text(text)


def _resolve_http_endpoint(kwargs: dict[str, Any]) -> str | None:
    if "http_endpoint" not in kwargs:
        return None
    raw_endpoint = kwargs["http_endpoint"]
    if raw_endpoint is None:
        return None
    if isinstance(raw_endpoint, str):
        return raw_endpoint
    return str(raw_endpoint)


def _resolve_llm_config(raw_config: dict[str, Any]) -> _LLMClientConfig:
    return _LLMClientConfig(
        route_policy=str(raw_config.get("llm_route_policy") or "codex_only").strip()
        or "codex_only",
        model=_optional_str(raw_config.get("model") or os.getenv("LLM_CLIENT_MODEL")),
        timeout_seconds=_optional_float(
            raw_config.get("timeout_seconds") or os.getenv("LLM_CLIENT_TIMEOUT_SECONDS")
        ),
        reasoning_effort=_optional_str(
            raw_config.get("reasoning_effort") or os.getenv("LLM_CLIENT_REASONING_EFFORT")
        ),
        reasoning_summary=_optional_str(
            raw_config.get("reasoning_summary") or os.getenv("LLM_CLIENT_REASONING_SUMMARY")
        ),
        text_verbosity=_optional_str(
            raw_config.get("text_verbosity") or os.getenv("LLM_CLIENT_TEXT_VERBOSITY")
        ),
    )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _restore_context_state(owner: AgentMuxBackend) -> None:
    persisted_context = owner.runtime_state.context_snapshot()
    context_generation = getattr(owner, "context_generation", 0)
    try:
        persisted_generation = persisted_context["context_generation"]
    except KeyError:
        persisted_generation = None
    if persisted_generation is not None:
        context_generation = int(persisted_generation)
    owner.context_generation = context_generation
    fallback_context_id = str(getattr(owner, "current_context_id", "")).strip()
    if not fallback_context_id:
        fallback_context_id = uuid.uuid4().hex[:12]
    owner.current_context_id = owner.runtime_state.ensure_context_id(
        fallback_context_id=fallback_context_id,
        generation=owner.context_generation,
    )
    owner.context.generation = owner.context_generation
    owner.context.current_id = owner.current_context_id


def _build_engine(owner: AgentMuxBackend) -> BackendRuntimeEngine:
    context_manager = ActiveContextManager(owner)
    process_controller = ProcessController(owner)
    owner._context_manager = context_manager
    owner._process_controller = process_controller
    return BackendRuntimeEngine(
        owner,
        context_manager,
        process_controller,
        EngineCallbacks(
            on_processing_event=owner._status.mark_processing_event,
            on_running_dispatch=owner._status.mark_running_dispatch,
            on_failed_dispatch=owner._status.mark_failed_dispatch,
            on_completed_dispatch=owner._status.mark_completed_dispatch,
        ),
    )


class AgentMuxBackend(BaseAgentBackend):
    _status: StatusTracker
    _context_manager: ActiveContextManager
    _process_controller: ProcessController
    context_generation: int

    last_queued_event_id = _StatusField("queued_event_id")
    last_queued_event_ids = _StatusField("queued_event_ids")
    last_duplicate_events = _StatusField("duplicate_events")
    last_dispatch_id = _StatusField("dispatch_id")
    last_dispatch_status = _StatusField("dispatch_status")
    last_dispatch_reason = _StatusField("dispatch_reason")
    last_reply_preview = _StatusField("reply_preview")
    last_processed_event_id = _StatusField("processed_event_id")
    last_processed_event_kind = _StatusField("processed_event_kind")
    last_tool_calls = _StatusField("tool_calls")

    def __init__(
        self,
        *,
        agent_slug: str,
        backend_type: str,
        working_dir: str,
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            agent_slug=agent_slug,
            backend_type=backend_type,
            working_dir=working_dir,
            config=config,
        )
        raw_config = dict(config or {})
        system_prompt = ""
        try:
            raw_system_prompt = kwargs["system_prompt"]
        except KeyError:
            raw_system_prompt = ""
        system_prompt = str(raw_system_prompt or "")
        self.system_prompt = system_prompt.strip()
        llm_config = _resolve_llm_config(raw_config)
        self.settings = backend_settings.build_runtime_settings(
            raw_config,
            working_dir=working_dir,
            http_endpoint=_resolve_http_endpoint(kwargs),
            llm_route_policy=llm_config.route_policy,
            llm_model=llm_config.model,
        )
        self.runtime_state = AgentMuxRuntimeState(self.settings.state_root)
        self.context_generation = self.context.generation
        self.current_context_id = self.context.current_id
        _restore_context_state(self)
        self._task_lock = asyncio.Lock()
        self._processor_task: asyncio.Task[None] | None = None
        self._active_process: asyncio.subprocess.Process | None = None
        self._active_dispatch_id: str | None = None
        self._active_event_payload: dict[str, Any] | None = None
        self._status = StatusTracker()
        self._engine = _build_engine(self)
        self._queue_processing_hooks = self._engine._queue_processing_hooks

    async def on_start(self) -> None:
        self.runtime_state.ensure_layout()
        self.current_context_id = self.runtime_state.ensure_context_id(
            fallback_context_id=self.current_context_id,
            generation=self.context_generation,
        )
        self.context.generation = self.context_generation
        self.context.current_id = self.current_context_id
        if self.runtime_state.queue_size() > 0:
            await self._process_controller.schedule_processor(processor=self._engine.process_queue)

    async def on_shutdown(self) -> None:
        await self._process_controller.cancel_runtime()
        self._context_manager.clear_active_context()

    async def handle_events(
        self,
        delivery: EventDelivery,
        *,
        is_interrupt: bool = False,
    ) -> EventDeliveryResult:
        _ = is_interrupt
        self.remember_delivery(delivery)
        queue_result = self.runtime_state.queue_delivery(delivery)
        self._status.mark_queued(
            queued_event_ids=list(queue_result["queued_event_ids"]),
            duplicate_events=int(queue_result["duplicate_events"]),
        )
        if any(event.interrupts_runtime for event in delivery.events):
            await self._process_controller.interrupt_active_dispatch(
                reason=f"incoming {delivery.events[-1].event_kind}"
            )
        if queue_result["queued_events"] > 0:
            await self._process_controller.schedule_processor(processor=self._engine.process_queue)
        return EventDeliveryResult(
            accepted=True,
            accepted_events=len(delivery.events),
            delivery_id=delivery.delivery_id,
            duplicate=bool(
                queue_result["queued_events"] == 0 and queue_result["duplicate_events"] > 0
            ),
            details={
                "backend_type": self.backend_type,
                "wrapper_mode": "agent_mux_codex_generic",
                "queue_size": queue_result["queue_size"],
                "queued_events": queue_result["queued_events"],
                "duplicate_events": queue_result["duplicate_events"],
                "queued_event_ids": queue_result["queued_event_ids"],
                "last_event_id": self.last_queued_event_id,
            },
        )

    async def stop(self, request: StopRequest) -> dict[str, Any]:
        payload = await super().stop(request)
        cleared_queue = 0
        if request.thread_id or request.parent_thread_id:
            cleared_queue = self.runtime_state.clear_entries_matching(
                thread_id=request.thread_id,
                parent_thread_id=request.parent_thread_id,
            )
            if self._context_manager.active_event_matches_filters(
                self._active_event_payload,
                thread_id=request.thread_id,
                parent_thread_id=request.parent_thread_id,
            ):
                await self._process_controller.interrupt_active_dispatch(reason=request.reason)
        else:
            await self._process_controller.interrupt_active_dispatch(reason=request.reason)
        payload.update(
            {
                "wrapper_mode": "agent_mux_codex_generic",
                "cleared_queue_events": cleared_queue,
            }
        )
        return payload

    async def last_status(self) -> dict[str, Any]:
        payload = await super().last_status()
        payload.update(
            {
                "http_endpoint": self.settings.http_endpoint,
                "wrapper_mode": "agent_mux_codex_generic",
                "agent_mux_binary": self.settings.agent_mux_binary,
                "llm_proxy_url": self.settings.llm_proxy_url,
                "llm_route_policy": self.settings.llm_route_policy,
                "default_model": self.settings.default_model,
                "configured_mcp_servers": [item["name"] for item in self.settings.mcp_servers],
                "require_tool_call_for_response": self.settings.require_tool_call_for_response,
                "last_queued_event_id": self.last_queued_event_id,
                "last_queued_event_ids": list(self.last_queued_event_ids),
                "last_duplicate_events": self.last_duplicate_events,
                "last_dispatch_id": self.last_dispatch_id,
                "last_dispatch_status": self.last_dispatch_status,
                "last_dispatch_reason": self.last_dispatch_reason,
                "last_reply_preview": self.last_reply_preview,
                "last_processed_event_id": self.last_processed_event_id,
                "last_processed_event_kind": self.last_processed_event_kind,
                "last_tool_calls": list(self.last_tool_calls),
                "runtime_context": self.runtime_state.context_snapshot(),
                "runtime_state": self.runtime_state.status_snapshot(),
                "active_dispatch_id": self._active_dispatch_id,
                "active_process_running": bool(
                    self._active_process and self._active_process.returncode is None
                ),
            }
        )
        return payload

    async def clear_context(self, request: ClearContextRequest) -> dict[str, Any]:
        previous_context_id = self.current_context_id
        payload = await super().clear_context(request)
        self.context_generation = self.context.generation
        self.current_context_id = self.context.current_id
        self.runtime_state.save_context_id(
            context_id=self.current_context_id,
            previous_context_id=previous_context_id,
            generation=self.context_generation,
        )
        self._context_manager.clear_active_context()
        await self._process_controller.cancel_runtime()
        self._processor_task = None
        self._active_process = None
        self._active_dispatch_id = None
        self._active_event_payload = None
        cleared_pending_entries = self.runtime_state.clear_all_pending_entries()
        self.runtime_state.reset_runtime_metadata()
        self._status.reset()
        payload.update(
            {
                "wrapper_mode": "agent_mux_codex_generic",
                "cleared_pending_entries": cleared_pending_entries,
                "runtime_context": self.runtime_state.context_snapshot(),
                "runtime_state": self.runtime_state.status_snapshot(),
            }
        )
        return payload
