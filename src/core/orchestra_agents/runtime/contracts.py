"""Standard HTTP contract shared by Orchestra agent runtimes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentEvent:
    """One delivered event for the agent runtime."""

    event_id: str | None
    thread_id: str | None
    root_thread_id: str | None
    parent_thread_id: str | None
    owner_agent_slug: str | None
    sequence_no: int | None
    event_kind: str
    notification_status: str | None
    from_agent_slug: str | None
    to_agent_slug: str | None
    message_text: str
    interrupts_runtime: bool
    requires_response: bool
    created_at: str | None
    raw_payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> AgentEvent:
        return cls(
            event_id=str(payload.get("event_id") or "").strip() or None,
            thread_id=str(payload.get("thread_id") or "").strip() or None,
            root_thread_id=str(payload.get("root_thread_id") or "").strip() or None,
            parent_thread_id=str(payload.get("parent_thread_id") or "").strip() or None,
            owner_agent_slug=str(payload.get("owner_agent_slug") or "").strip() or None,
            sequence_no=int(payload["sequence_no"])
            if payload.get("sequence_no") is not None
            else None,
            event_kind=str(payload.get("event_kind") or "message").strip() or "message",
            notification_status=str(payload.get("notification_status") or "").strip() or None,
            from_agent_slug=str(payload.get("from_agent_slug") or "").strip() or None,
            to_agent_slug=str(payload.get("to_agent_slug") or "").strip() or None,
            message_text=str(payload.get("message_text") or ""),
            interrupts_runtime=bool(payload.get("interrupts_runtime")),
            requires_response=bool(payload.get("requires_response")),
            created_at=str(payload.get("created_at") or "").strip() or None,
            raw_payload=dict(payload),
        )


@dataclass(frozen=True)
class EventDelivery:
    """One delivery batch from the control plane."""

    delivery_id: str | None
    events: list[AgentEvent]
    raw_payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> EventDelivery:
        events_raw = payload.get("events")
        if not isinstance(events_raw, list) or not events_raw:
            raise ValueError("events are required")
        return cls(
            delivery_id=str(payload.get("delivery_id") or "").strip() or None,
            events=[
                AgentEvent.from_dict(dict(item)) for item in events_raw if isinstance(item, dict)
            ],
            raw_payload=dict(payload),
        )


@dataclass(frozen=True)
class EventDeliveryResult:
    """Normalized delivery acknowledgement."""

    accepted: bool
    accepted_events: int
    delivery_id: str | None = None
    duplicate: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "accepted": self.accepted,
            "accepted_events": self.accepted_events,
            "delivery_id": self.delivery_id or "",
            "duplicate": self.duplicate,
        }
        payload.update(self.details)
        return payload


@dataclass(frozen=True)
class StopRequest:
    """Control-plane stop request."""

    reason: str
    thread_id: str | None
    parent_thread_id: str | None
    raw_payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> StopRequest:
        return cls(
            reason=str(payload.get("reason") or "stop requested").strip() or "stop requested",
            thread_id=str(payload.get("thread_id") or "").strip() or None,
            parent_thread_id=str(payload.get("parent_thread_id") or "").strip() or None,
            raw_payload=dict(payload),
        )


@dataclass(frozen=True)
class ClearContextRequest:
    """Control-plane context reset request."""

    requested_by: str | None
    raw_payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ClearContextRequest:
        return cls(
            requested_by=str(payload.get("requested_by") or "").strip() or None,
            raw_payload=dict(payload),
        )
