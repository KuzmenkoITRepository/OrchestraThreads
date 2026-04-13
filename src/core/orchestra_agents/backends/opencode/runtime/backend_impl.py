from __future__ import annotations

import asyncio
from typing import Any

from core.orchestra_agents.backends.opencode import (
    backend_dispatch,
    backend_registration,
    backend_runtime,
    backend_state,
)
from core.orchestra_agents.backends.opencode.backend_context import clear_file
from core.orchestra_agents.backends.opencode.backend_status import build_status_extras
from core.orchestra_agents.runtime import (
    BaseAgentBackend,
    ClearContextRequest,
    EventDelivery,
    EventDeliveryResult,
    StopRequest,
)
from core.orchestra_thread.client import OrchestraThreadsClient

_DEFAULT_SERVE_PORT = 4096
_DEFAULT_DISPATCH_TIMEOUT = 120.0
_DEFAULT_READY_TIMEOUT = 20.0
_SEEN_IDS_LIMIT = 1000


class OpencodeOmoBackend(BaseAgentBackend):
    def __init__(
        self,
        *,
        agent_slug: str,
        backend_type: str,
        working_dir: str,
        **kwargs: Any,
    ) -> None:
        raw_config = dict(kwargs.get("config") or {})
        super().__init__(
            agent_slug=agent_slug,
            backend_type=backend_type,
            working_dir=working_dir,
            config=raw_config,
        )
        self.system_prompt = str(kwargs.get("system_prompt") or "").strip()
        self.http_endpoint = _optional_str(kwargs.get("http_endpoint"))
        self._paths = backend_state.RuntimePaths.from_working_dir(working_dir)
        self._serve_port = _to_int(raw_config.get("opencode_serve_port"), _DEFAULT_SERVE_PORT)
        self._dispatch_timeout = _to_float(
            raw_config.get("dispatch_timeout_seconds"),
            _DEFAULT_DISPATCH_TIMEOUT,
        )
        self._ready_timeout = _to_float(
            raw_config.get("startup_timeout_seconds"),
            _DEFAULT_READY_TIMEOUT,
        )
        self._components = backend_state.Components()
        self._dispatch = backend_state.DispatchState()
        self._dedup = backend_state.DedupState(limit=_SEEN_IDS_LIMIT)
        self._threads_client: OrchestraThreadsClient | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None

    async def on_start(self) -> None:
        self._paths.ensure()
        params = backend_runtime.ComponentParams(
            paths=self._paths,
            config=self.config,
            agent_slug=self.agent_slug,
            working_dir=self.working_dir,
            serve_port=self._serve_port,
            ready_timeout=self._ready_timeout,
        )
        self._components = await backend_runtime.start_components(params)
        await backend_registration.register_with_threads(self)

    async def handle_events(self, delivery: EventDelivery) -> EventDeliveryResult:
        self.remember_delivery(delivery)
        dispatchable, duplicate_count, queued_ids = backend_dispatch.classify_events(
            delivery.events,
            self._dedup,
        )
        for event in dispatchable:
            backend_dispatch.fire_dispatch(self, event)
        return EventDeliveryResult(
            accepted=True,
            accepted_events=len(delivery.events),
            delivery_id=delivery.delivery_id,
            duplicate=not dispatchable and duplicate_count > 0,
            details={
                "backend_type": self.backend_type,
                "wrapper_mode": "opencode_omo",
                "queued_events": len(dispatchable),
                "duplicate_events": duplicate_count,
                "queued_event_ids": queued_ids,
            },
        )

    async def on_shutdown(self) -> None:
        await backend_registration.stop_registration(self)
        await backend_dispatch.cancel_dispatch(self._dispatch)
        await backend_runtime.shutdown_components(self._components)

    async def stop(self, request: StopRequest) -> dict[str, Any]:
        if backend_dispatch.dispatch_matches(
            self._dispatch,
            request.thread_id,
            request.parent_thread_id,
        ):
            await backend_dispatch.cancel_dispatch(self._dispatch)
        payload = await super().stop(request)
        payload["wrapper_mode"] = "opencode_omo"
        return payload

    async def clear_context(self, request: ClearContextRequest) -> dict[str, Any]:
        manager = self._components.session_manager
        if manager is not None:
            await manager.delete_session(self.context.current_id)
        payload = await super().clear_context(request)
        clear_file(self._paths.active_context)
        payload["wrapper_mode"] = "opencode_omo"
        return payload

    async def last_status(self) -> dict[str, Any]:
        payload = await super().last_status()
        payload.update(
            build_status_extras(
                self._components,
                self._serve_port,
                self._dispatch,
            )
        )
        return payload


def _optional_str(raw_value: object) -> str | None:
    if raw_value is None:
        return None
    normalized = str(raw_value).strip()
    return normalized or None


def _to_int(raw_value: object, fallback: int) -> int:
    if raw_value is None:
        return fallback
    if not isinstance(raw_value, (int, float, str)):
        return fallback
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return fallback


def _to_float(raw_value: object, fallback: float) -> float:
    if raw_value is None:
        return fallback
    if not isinstance(raw_value, (int, float, str)):
        return fallback
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return fallback
