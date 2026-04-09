"""Lookup-row mapping for ingest service point reads."""

from __future__ import annotations

from datetime import datetime

from core.agent_log_analysis.api_models import GetEventResult
from core.agent_log_analysis.validation_time import parse_timestamp, serialize_timestamp


def map_event_lookup(
    row: dict[str, object],
    *,
    labels: dict[str, str],
) -> GetEventResult:
    """Map a stored row into the point-lookup DTO."""
    payload_json = _mapping(row.get("payload_json"))
    metadata = _metadata(row, payload_json)
    return GetEventResult(
        event_id=_required_text(row, "event_id"),
        event_type=_required_text(row, "event_type"),
        occurred_at=_serialize_row_time(row.get("occurred_at"), field_name="occurred_at"),
        received_at=_serialize_row_time(row.get("received_at"), field_name="received_at"),
        agent_slug=_required_text(row, "agent_slug"),
        run_id=_optional_text(row.get("run_id")),
        thread_id=_optional_text(row.get("thread_id")),
        correlation_id=_optional_text(row.get("correlation_id")),
        parent_event_id=_optional_text(row.get("parent_event_id")),
        status=_optional_text(row.get("status")),
        labels=labels,
        metadata=metadata,
        payload=_payload_data(payload_json),
        raw_payload_attached=bool(row.get("raw_payload_attached", False)),
    )


def _serialize_row_time(value: object, *, field_name: str) -> str:
    if isinstance(value, datetime):
        return serialize_timestamp(value)
    return serialize_timestamp(parse_timestamp(value, field_name=field_name))


def _payload_data(payload_json: dict[str, object]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in payload_json.items():
        if key not in {"labels", "metadata"}:
            payload[key] = value
    return payload


def _metadata(
    row: dict[str, object],
    payload_json: dict[str, object],
) -> dict[str, object]:
    row_metadata = _mapping(row.get("metadata_json"))
    if row_metadata:
        return row_metadata
    return _mapping(payload_json.get("metadata"))


def _mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _required_text(row: dict[str, object], field_name: str) -> str:
    value = row.get(field_name)
    return value if isinstance(value, str) else ""


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) else None
