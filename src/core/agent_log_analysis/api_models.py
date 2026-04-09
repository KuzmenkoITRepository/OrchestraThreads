"""Request and response DTOs for the agent log analysis API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class IngestEventRequest:
    """Single event ingestion request."""

    event_id: str
    event_type: str
    occurred_at: str
    agent_slug: str
    run_id: str | None = None
    thread_id: str | None = None
    correlation_id: str | None = None
    parent_event_id: str | None = None
    labels: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_payload: dict[str, Any] | None = None
    inference: dict[str, Any] | None = None
    action: dict[str, Any] | None = None
    raw_logs: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class IngestBatchRequest:
    """Batch event ingestion request."""

    events: list[IngestEventRequest]


@dataclass(frozen=True)
class IngestEventResult:
    """Result of a single event ingestion."""

    event_id: str
    status: str
    duplicate: bool = False
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class GetEventResult:
    """Result of a single event lookup."""

    event_id: str
    event_type: str
    occurred_at: str
    received_at: str
    agent_slug: str
    run_id: str | None = None
    thread_id: str | None = None
    correlation_id: str | None = None
    parent_event_id: str | None = None
    status: str | None = None
    labels: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    payload: dict[str, Any] = field(default_factory=dict)
    raw_payload_attached: bool = False
