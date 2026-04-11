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


class _PayloadState:
    preview_max_len = 120
    preview_truncated_len = 117
    state_idle = "idle"
    state_stopped = "stopped"
    default_interrupt_message = "interrupt not implemented in base backend"

    @staticmethod
    def message_preview(message_text: str) -> str | None:
        preview = " ".join(message_text.split())
        if len(preview) > _PayloadState.preview_max_len:
            preview = f"{preview[: _PayloadState.preview_truncated_len]}..."
        return preview or None

    @staticmethod
    def lifecycle_state(stop_reason: str | None) -> str:
        return _PayloadState.state_idle if stop_reason is None else _PayloadState.state_stopped


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
        self.last_message_preview = _PayloadState.message_preview(event.message_text)


@dataclass
class _ContextState:
    generation: int = 0
    current_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def rotate(self) -> str:
        previous = self.current_id
        self.generation += 1
        self.current_id = uuid.uuid4().hex[:12]
        return previous


class _PayloadResponses:
    @staticmethod
    def stop(
        *,
        reason: str,
        thread_id: str | None,
        parent_thread_id: str | None,
    ) -> dict[str, Any]:
        return {
            "success": True,
            "stop_reason": reason,
            "thread_id": thread_id,
            "parent_thread_id": parent_thread_id,
        }

    @staticmethod
    def clear_context(
        *,
        generation: int,
        current_id: str,
        previous_id: str,
    ) -> dict[str, Any]:
        return {
            "success": True,
            "context_generation": generation,
            "context_id": current_id,
            "previous_context_id": previous_id,
        }

    @staticmethod
    def reset_session(
        *,
        routing_key: str,
        generation: int,
        current_id: str,
        previous_id: str,
    ) -> dict[str, Any]:
        return {
            "success": True,
            "routing_key": routing_key,
            "context_generation": generation,
            "context_id": current_id,
            "previous_context_id": previous_id,
        }

    @staticmethod
    def session_state(
        *,
        routing_key: str,
        stop_reason: str | None,
        context_id: str,
        last_delivery_id: str | None,
    ) -> dict[str, Any]:
        return {
            "routing_key": routing_key,
            "lifecycle": _PayloadState.lifecycle_state(stop_reason),
            "context_id": context_id,
            "last_delivery_id": last_delivery_id,
        }

    @staticmethod
    def interrupt(routing_key: str) -> dict[str, Any]:
        return {
            "success": True,
            "routing_key": routing_key,
            "message": _PayloadState.default_interrupt_message,
        }

    @staticmethod
    def status(
        *,
        agent_slug: str,
        backend_type: str,
        generation: int,
        context_id: str,
        delivery: _DeliveryState,
    ) -> dict[str, Any]:
        return {
            "agent_slug": agent_slug,
            "backend_type": backend_type,
            "context_generation": generation,
            "context_id": context_id,
            "last_delivery_id": delivery.last_delivery_id,
            "last_event_kind": delivery.last_event_kind,
            "last_message_preview": delivery.last_message_preview,
            "stop_reason": delivery.stop_reason,
            "state": _PayloadState.lifecycle_state(delivery.stop_reason),
        }

    @staticmethod
    def health(
        *,
        agent_slug: str,
        backend_type: str,
        context_id: str,
        stop_reason: str | None,
    ) -> dict[str, Any]:
        return {
            "status": "ok",
            "agent_slug": agent_slug,
            "backend_type": backend_type,
            "context_id": context_id,
            "state": _PayloadState.lifecycle_state(stop_reason),
        }


class _BackendLifecycleOps:
    delivery: _DeliveryState
    context: _ContextState

    async def on_start(self) -> None:
        """Optional startup hook."""

    async def on_shutdown(self) -> None:
        """Optional shutdown hook."""

    async def stop(self, request: StopRequest) -> dict[str, Any]:
        self.delivery.stop_reason = request.reason
        return _PayloadResponses.stop(
            reason=request.reason,
            thread_id=request.thread_id,
            parent_thread_id=request.parent_thread_id,
        )

    async def clear_context(self, _request: ClearContextRequest) -> dict[str, Any]:
        previous = self.context.rotate()
        self.delivery.reset()
        return _PayloadResponses.clear_context(
            generation=self.context.generation,
            current_id=self.context.current_id,
            previous_id=previous,
        )


class _BackendStatusOps:
    agent_slug: str
    backend_type: str
    delivery: _DeliveryState
    context: _ContextState

    async def last_status(self) -> dict[str, Any]:
        return _PayloadResponses.status(
            agent_slug=self.agent_slug,
            backend_type=self.backend_type,
            generation=self.context.generation,
            context_id=self.context.current_id,
            delivery=self.delivery,
        )

    async def health(self) -> dict[str, Any]:
        return _PayloadResponses.health(
            agent_slug=self.agent_slug,
            backend_type=self.backend_type,
            context_id=self.context.current_id,
            stop_reason=self.delivery.stop_reason,
        )

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

    async def reset_session(self, routing_key: str) -> dict[str, Any]:
        """
        Reset session for a routing key.

        Default implementation rotates context (backward compat).
        Subclasses should override for session-aware behavior.
        """
        previous = self.context.rotate()
        self.delivery.reset()
        return _PayloadResponses.reset_session(
            routing_key=routing_key,
            generation=self.context.generation,
            current_id=self.context.current_id,
            previous_id=previous,
        )

    async def get_session_state(self, routing_key: str) -> dict[str, Any]:
        """
        Get session state for a routing key.

        Default implementation returns basic backend state.
        Subclasses should override for session-aware behavior.
        """
        return _PayloadResponses.session_state(
            routing_key=routing_key,
            stop_reason=self.delivery.stop_reason,
            context_id=self.context.current_id,
            last_delivery_id=self.delivery.last_delivery_id,
        )

    async def interrupt_session(self, routing_key: str) -> dict[str, Any]:
        """
        Interrupt session for a routing key.

        Default implementation is a no-op.
        Subclasses should override for session-aware behavior.
        """
        return _PayloadResponses.interrupt(routing_key)
