"""Low-level ingest parsing helpers."""

from __future__ import annotations

from typing import Any

from core.agent_log_analysis.api_models import IngestBatchRequest, IngestEventRequest
from core.agent_log_analysis.errors import ValidationError
from core.agent_log_analysis.validation_json import coerce_mapping, coerce_optional_mapping
from core.agent_log_analysis.validation_scalars import optional_text


def coerce_event_request(payload: Any) -> IngestEventRequest:
    """Coerce a raw payload into an ingest request DTO."""
    if isinstance(payload, IngestEventRequest):
        return payload
    mapping = coerce_mapping(payload, field_name="ingest event")
    return IngestEventRequest(
        event_id=str(mapping.get("event_id") or ""),
        event_type=str(mapping.get("event_type") or ""),
        occurred_at=str(mapping.get("occurred_at") or ""),
        agent_slug=str(mapping.get("agent_slug") or ""),
        run_id=optional_text(mapping.get("run_id")),
        thread_id=optional_text(mapping.get("thread_id")),
        correlation_id=optional_text(mapping.get("correlation_id")),
        parent_event_id=optional_text(mapping.get("parent_event_id")),
        labels=coerce_mapping(mapping.get("labels", {}), field_name="labels"),
        metadata=coerce_mapping(mapping.get("metadata", {}), field_name="metadata"),
        raw_payload=coerce_optional_mapping(
            mapping.get("raw_payload"),
            field_name="raw_payload",
        ),
        inference=coerce_optional_mapping(
            mapping.get("inference"),
            field_name="inference",
        ),
        action=coerce_optional_mapping(mapping.get("action"), field_name="action"),
        raw_logs=_coerce_raw_logs(mapping.get("raw_logs", [])),
    )


def coerce_batch_request(payload: Any) -> IngestBatchRequest:
    """Coerce a raw payload into a batch ingest DTO."""
    if isinstance(payload, IngestBatchRequest):
        return payload
    mapping = coerce_mapping(payload, field_name="batch ingest payload")
    raw_events = mapping.get("events")
    if not isinstance(raw_events, list):
        raise ValidationError("VALIDATION_ERROR", "events must be a list")
    return IngestBatchRequest(events=[coerce_event_request(item) for item in raw_events])


def _coerce_raw_logs(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise ValidationError("VALIDATION_ERROR", "raw_logs must be a list")
    raw_logs: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValidationError("VALIDATION_ERROR", "raw_logs items must be objects")
        raw_logs.append(dict(item))
    return raw_logs
