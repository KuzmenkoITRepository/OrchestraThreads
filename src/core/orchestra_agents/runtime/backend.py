"""Backend abstraction for standard Orchestra agents."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from core.orchestra_agents.runtime.contracts import (
    ClearContextRequest,
    EventDelivery,
    EventDeliveryResult,
    StopRequest,
)

_PREVIEW_MAX_LEN = 120
_PREVIEW_TRUNCATED_LEN = 117


@dataclass
class _DeliveryState:
    last_delivery_id: str | None = None
    last_event_kind: str | None = None
    last_message_preview: str | None = None
    stop_reason: str | None = None

    def reset(self) -> None:
        self.last_delivery_id = None
        self.last_event_kind = None
        self.last_message_preview = None
        self.stop_reason = None

    def remember(self, delivery: EventDelivery) -> None:
        self.last_delivery_id = delivery.delivery_id
        if not delivery.events:
            return
        event = delivery.events[-1]
        self.last_event_kind = event.event_kind
        preview = " ".join(event.message_text.split())
        if len(preview) > _PREVIEW_MAX_LEN:
            preview = f"{preview[:_PREVIEW_TRUNCATED_LEN]}..."
        self.last_message_preview = preview or None


@dataclass
class _ContextState:
    generation: int = 0
    current_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def rotate(self) -> str:
        previous = self.current_id
        self.generation += 1
        self.current_id = uuid.uuid4().hex[:12]
        return previous


class _BackendLifecycleOps:
    delivery: _DeliveryState
    context: _ContextState

    async def on_start(self) -> None:
        """Optional startup hook."""

    async def on_shutdown(self) -> None:
        """Optional shutdown hook."""

    async def stop(self, request: StopRequest) -> dict[str, Any]:
        self.delivery.stop_reason = request.reason
        return {
            "success": True,
            "stop_reason": request.reason,
            "thread_id": request.thread_id,
            "parent_thread_id": request.parent_thread_id,
        }

    async def clear_context(self, _request: ClearContextRequest) -> dict[str, Any]:
        previous = self.context.rotate()
        self.delivery.reset()
        return {
            "success": True,
            "context_generation": self.context.generation,
            "context_id": self.context.current_id,
            "previous_context_id": previous,
        }


class _BackendStatusOps:
    agent_slug: str
    backend_type: str
    delivery: _DeliveryState
    context: _ContextState

    async def last_status(self) -> dict[str, Any]:
        return _build_status_payload(self)

    async def health(self) -> dict[str, Any]:
        return _build_health_payload(self)

    def remember_delivery(self, delivery: EventDelivery) -> None:
        self.delivery.remember(delivery)


class BaseAgentBackend(_BackendLifecycleOps, _BackendStatusOps, ABC):
    """Minimal backend surface used by the shared HTTP runtime."""

    def __init__(
        self,
        *,
        agent_slug: str,
        backend_type: str,
        working_dir: str,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.agent_slug = agent_slug
        self.backend_type = backend_type
        self.working_dir = working_dir
        self.config = dict(config or {})
        self.delivery = _DeliveryState()
        self.context = _ContextState()

    @abstractmethod
    async def handle_events(self, delivery: EventDelivery) -> EventDeliveryResult:
        """Handle one delivery batch."""


def _build_status_payload(backend: _BackendStatusOps) -> dict[str, Any]:
    return {
        "agent_slug": backend.agent_slug,
        "backend_type": backend.backend_type,
        "context_generation": backend.context.generation,
        "context_id": backend.context.current_id,
        "last_delivery_id": backend.delivery.last_delivery_id,
        "last_event_kind": backend.delivery.last_event_kind,
        "last_message_preview": backend.delivery.last_message_preview,
        "stop_reason": backend.delivery.stop_reason,
        "state": "idle" if backend.delivery.stop_reason is None else "stopped",
    }


def _build_health_payload(backend: _BackendStatusOps) -> dict[str, Any]:
    return {
        "status": "ok",
        "agent_slug": backend.agent_slug,
        "backend_type": backend.backend_type,
        "context_id": backend.context.current_id,
        "state": "idle" if backend.delivery.stop_reason is None else "stopped",
    }
