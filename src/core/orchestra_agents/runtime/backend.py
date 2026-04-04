"""Backend abstraction for standard Orchestra agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional
import uuid

from .contracts import ClearContextRequest, EventDelivery, EventDeliveryResult, StopRequest


class BaseAgentBackend(ABC):
    """Minimal backend surface used by the shared HTTP runtime."""

    def __init__(
        self,
        *,
        agent_slug: str,
        backend_type: str,
        working_dir: str,
        config: Optional[dict[str, Any]] = None,
    ) -> None:
        self.agent_slug = agent_slug
        self.backend_type = backend_type
        self.working_dir = working_dir
        self.config = dict(config or {})
        self.last_delivery_id: Optional[str] = None
        self.last_event_kind: Optional[str] = None
        self.last_message_preview: Optional[str] = None
        self.stop_reason: Optional[str] = None
        self.context_generation = 0
        self.current_context_id = self._generate_context_id()

    @staticmethod
    def _generate_context_id() -> str:
        return uuid.uuid4().hex[:12]

    async def on_start(self) -> None:
        """Optional startup hook."""

    async def on_shutdown(self) -> None:
        """Optional shutdown hook."""

    @abstractmethod
    async def handle_events(self, delivery: EventDelivery) -> EventDeliveryResult:
        """Handle one delivery batch."""

    async def stop(self, request: StopRequest) -> dict[str, Any]:
        self.stop_reason = request.reason
        return {
            "success": True,
            "stop_reason": request.reason,
            "thread_id": request.thread_id,
            "parent_thread_id": request.parent_thread_id,
        }

    async def last_status(self) -> dict[str, Any]:
        return {
            "agent_slug": self.agent_slug,
            "backend_type": self.backend_type,
            "context_generation": self.context_generation,
            "context_id": self.current_context_id,
            "last_delivery_id": self.last_delivery_id,
            "last_event_kind": self.last_event_kind,
            "last_message_preview": self.last_message_preview,
            "stop_reason": self.stop_reason,
            "state": "idle" if self.stop_reason is None else "stopped",
        }

    async def clear_context(self, request: ClearContextRequest) -> dict[str, Any]:
        del request
        previous_context_id = self.current_context_id
        self.context_generation += 1
        self.current_context_id = self._generate_context_id()
        self.last_delivery_id = None
        self.last_event_kind = None
        self.last_message_preview = None
        self.stop_reason = None
        return {
            "success": True,
            "context_generation": self.context_generation,
            "context_id": self.current_context_id,
            "previous_context_id": previous_context_id,
        }

    async def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "agent_slug": self.agent_slug,
            "backend_type": self.backend_type,
            "context_id": self.current_context_id,
            "state": "idle" if self.stop_reason is None else "stopped",
        }

    def remember_delivery(self, delivery: EventDelivery) -> None:
        self.last_delivery_id = delivery.delivery_id
        if not delivery.events:
            return
        event = delivery.events[-1]
        self.last_event_kind = event.event_kind
        preview = " ".join(event.message_text.split())
        if len(preview) > 120:
            preview = f"{preview[:117]}..."
        self.last_message_preview = preview or None
