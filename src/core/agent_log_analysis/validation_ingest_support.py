"""Support types and builders for ingest validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.agent_log_analysis import validation_ingest_payloads as ingest_payloads
from core.agent_log_analysis import validation_ingest_records as ingest_records
from core.agent_log_analysis.api_models import IngestEventRequest
from core.agent_log_analysis.config import AgentLogAnalysisConfig
from core.agent_log_analysis.event_envelope import EventType
from core.agent_log_analysis.validation_ingest_enums import parse_event_type
from core.agent_log_analysis.validation_ingest_labels import normalize_labels
from core.agent_log_analysis.validation_scalars import required_text
from core.agent_log_analysis.validation_time import parse_timestamp


@dataclass(frozen=True)
class NormalizedEventContext:
    """Canonical normalized event identity and time fields."""

    event_id: str
    agent_slug: str
    event_type: EventType
    occurred_at: datetime


@dataclass(frozen=True)
class NormalizedPayloadParts:
    """Normalized payload fragments for one ingest event."""

    labels: dict[str, str]
    metadata: dict[str, object]
    raw_payload: dict[str, object] | None
    inference: dict[str, object] | None
    action: dict[str, object] | None


def build_context(request: IngestEventRequest) -> NormalizedEventContext:
    """Build normalized event identity and time context."""
    return NormalizedEventContext(
        event_id=required_text(request.event_id, field_name="event_id"),
        agent_slug=required_text(request.agent_slug, field_name="agent_slug"),
        event_type=parse_event_type(request.event_type),
        occurred_at=parse_timestamp(request.occurred_at, field_name="occurred_at"),
    )


def normalize_payload_parts(
    request: IngestEventRequest,
    *,
    config: AgentLogAnalysisConfig,
) -> NormalizedPayloadParts:
    """Normalize the configurable payload sections of an ingest request."""
    return NormalizedPayloadParts(
        labels=normalize_labels(
            request.labels,
            max_labels=config.max_labels_per_event,
        ),
        metadata=ingest_payloads.normalize_metadata(
            request.metadata,
            max_bytes=config.max_metadata_bytes,
        ),
        raw_payload=ingest_payloads.normalize_raw_payload(
            request.raw_payload,
            max_bytes=config.max_raw_payload_bytes,
        ),
        inference=ingest_records.normalize_inference(
            request.inference,
            max_error_bytes=config.max_error_message_bytes,
        ),
        action=ingest_records.normalize_action(
            request.action,
            max_error_bytes=config.max_error_message_bytes,
        ),
    )


def event_defaults(
    request: IngestEventRequest,
    *,
    context: NormalizedEventContext,
) -> dict[str, str | None]:
    """Build default raw-log scope inherited from the parent event."""
    return {
        "event_id": context.event_id,
        "agent_slug": context.agent_slug,
        "run_id": request.run_id,
        "thread_id": request.thread_id,
        "correlation_id": request.correlation_id,
    }
