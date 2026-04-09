"""Event-row builders for validated ingest requests."""

from __future__ import annotations

from datetime import datetime

from core.agent_log_analysis.api_models import IngestEventRequest
from core.agent_log_analysis.validation_time import parse_timestamp


def build_event_row(
    request: IngestEventRequest,
    *,
    received_at: datetime,
) -> dict[str, object]:
    """Build one normalized event-store row."""
    derived = _derived_fields(request)
    return {
        "event_id": request.event_id,
        "event_type": request.event_type,
        "occurred_at": parse_timestamp(request.occurred_at, field_name="occurred_at"),
        "received_at": received_at,
        "agent_slug": request.agent_slug,
        "run_id": request.run_id,
        "thread_id": request.thread_id,
        "correlation_id": request.correlation_id,
        "parent_event_id": request.parent_event_id,
        "status": derived["status"],
        "model_name": derived["model_name"],
        "provider_name": derived["provider_name"],
        "request_kind": derived["request_kind"],
        "action_kind": derived["action_kind"],
        "target_name": derived["target_name"],
        "target_agent_slug": derived["target_agent_slug"],
        "latency_ms": derived["latency_ms"],
        "metadata_json": request.metadata,
        "payload_json": _payload_json(request),
        "raw_payload_attached": request.raw_payload is not None,
    }


def _payload_json(request: IngestEventRequest) -> dict[str, object]:
    payload: dict[str, object] = {
        "labels": request.labels,
        "metadata": request.metadata,
        "raw_logs": request.raw_logs,
    }
    if request.raw_payload is not None:
        payload["raw_payload"] = request.raw_payload
    if request.inference is not None:
        payload["inference"] = request.inference
    if request.action is not None:
        payload["action"] = request.action
    return payload


def _derived_fields(request: IngestEventRequest) -> dict[str, object | None]:
    inference = request.inference
    action = request.action
    return {
        "status": _text_from(inference, "status") or _text_from(action, "status"),
        "model_name": _text_from(inference, "model_name"),
        "provider_name": _text_from(inference, "provider_name"),
        "request_kind": _text_from(inference, "request_kind"),
        "action_kind": _text_from(action, "action_kind"),
        "target_name": _text_from(action, "target_name"),
        "target_agent_slug": _text_from(action, "target_agent_slug"),
        "latency_ms": _int_from(inference, "latency_ms") or _int_from(action, "latency_ms"),
    }


def _text_from(payload: dict[str, object] | None, field_name: str) -> str | None:
    if payload is None:
        return None
    value = payload.get(field_name)
    return value if isinstance(value, str) else None


def _int_from(payload: dict[str, object] | None, field_name: str) -> int | None:
    if payload is None:
        return None
    value = payload.get(field_name)
    return value if isinstance(value, int) and not isinstance(value, bool) else None
