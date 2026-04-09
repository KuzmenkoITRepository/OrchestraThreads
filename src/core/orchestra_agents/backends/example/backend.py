"""Minimal canonical backend used by the generic scaffold template."""

from __future__ import annotations

from core.orchestra_agents.runtime import BaseAgentBackend, EventDelivery, EventDeliveryResult


class TemplateBackend(BaseAgentBackend):
    """Small example backend that only records the latest delivery."""

    async def handle_events(self, delivery: EventDelivery) -> EventDeliveryResult:
        self.remember_delivery(delivery)
        return EventDeliveryResult(
            accepted=True,
            accepted_events=len(delivery.events),
            delivery_id=delivery.delivery_id,
            details={
                "backend_type": self.backend_type,
                "last_thread_id": delivery.events[-1].thread_id if delivery.events else None,
            },
        )
