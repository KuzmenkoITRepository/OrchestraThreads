"""Standard HTTP contract shared by Orchestra agent runtimes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _opt_str(payload: dict[str, Any], key: str) -> str | None:
    return str(payload.get(key) or "").strip() or None


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
        """Build an AgentEvent from a raw dict."""
        seq = payload.get("sequence_no")
        return cls(
            event_id=_opt_str(payload, "event_id"),
            thread_id=_opt_str(payload, "thread_id"),
            root_thread_id=_opt_str(payload, "root_thread_id"),
            parent_thread_id=_opt_str(payload, "parent_thread_id"),
            owner_agent_slug=_opt_str(payload, "owner_agent_slug"),
            sequence_no=None if seq is None else int(seq),
            event_kind=str(payload.get("event_kind") or "message").strip() or "message",
            notification_status=_opt_str(payload, "notification_status"),
            from_agent_slug=_opt_str(payload, "from_agent_slug"),
            to_agent_slug=_opt_str(payload, "to_agent_slug"),
            message_text=str(payload.get("message_text") or ""),
            interrupts_runtime=bool(payload.get("interrupts_runtime")),
            requires_response=bool(payload.get("requires_response")),
            created_at=_opt_str(payload, "created_at"),
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
        """Build an EventDelivery from a raw dict."""
        events_raw = payload.get("events")
        if not isinstance(events_raw, list) or not events_raw:
            raise ValueError("events are required")
        return cls(
            delivery_id=_opt_str(payload, "delivery_id"),
            events=[AgentEvent.from_dict(dict(ev)) for ev in events_raw if isinstance(ev, dict)],
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
        """Serialize to a JSON-compatible dict."""
        payload: dict[str, Any] = {
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
        """Build a StopRequest from a raw dict."""
        return cls(
            reason=str(payload.get("reason") or "stop requested").strip() or "stop requested",
            thread_id=_opt_str(payload, "thread_id"),
            parent_thread_id=_opt_str(payload, "parent_thread_id"),
            raw_payload=dict(payload),
        )


@dataclass(frozen=True)
class ClearContextRequest:
    """Control-plane context reset request."""

    requested_by: str | None
    raw_payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ClearContextRequest:
        """Build a ClearContextRequest from a raw dict."""
        return cls(
            requested_by=_opt_str(payload, "requested_by"),
            raw_payload=dict(payload),
        )
