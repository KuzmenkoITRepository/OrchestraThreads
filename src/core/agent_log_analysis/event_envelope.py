"""Canonical event envelope for agent telemetry."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class EventType(StrEnum):
    """Normalized event type."""

    inference_event = "inference_event"
    action_event = "action_event"


@dataclass(frozen=True)
class EventEnvelope:
    """Top-level event envelope shared by all telemetry event types."""

    event_id: str
    event_type: EventType
    occurred_at: datetime
    received_at: datetime
    agent_slug: str
    run_id: str | None = None
    thread_id: str | None = None
    correlation_id: str | None = None
    parent_event_id: str | None = None
    labels: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_payload: dict[str, Any] | None = None
