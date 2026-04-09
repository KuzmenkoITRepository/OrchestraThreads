"""Shared mapping helpers for event-query and timeline services."""

from __future__ import annotations

from datetime import datetime

from core.agent_log_analysis.api_models import GetEventResult
from core.agent_log_analysis.ingest_service_lookup import map_event_lookup
from core.agent_log_analysis.validation_time import parse_timestamp, serialize_timestamp


def map_event_row(row: dict[str, object]) -> GetEventResult:
    """Map one stored row into the public event DTO."""
    return map_event_lookup(row, labels=_extract_labels(row))


def map_event_rows(rows: list[dict[str, object]]) -> list[GetEventResult]:
    """Map stored rows into public event DTOs."""
    return [map_event_row(row) for row in rows]


def build_next_cursor(rows: list[dict[str, object]], *, limit: int) -> str | None:
    """Build the stable page cursor from the last row."""
    if not rows or len(rows) < limit:
        return None
    last_row = rows[-1]
    occurred_at = _serialize_row_time(last_row.get("occurred_at"))
    event_id = _required_text(last_row, "event_id")
    return f"{occurred_at}|{event_id}"


def serialize_window(value: datetime) -> str:
    """Serialize a validated query window boundary."""
    return serialize_timestamp(value)


def _extract_labels(row: dict[str, object]) -> dict[str, str]:
    payload = row.get("payload_json")
    if not isinstance(payload, dict):
        return {}
    labels = payload.get("labels")
    return dict(labels) if isinstance(labels, dict) else {}


def _serialize_row_time(value: object) -> str:
    if isinstance(value, datetime):
        return serialize_timestamp(value)
    return serialize_timestamp(parse_timestamp(value, field_name="occurred_at"))


def _required_text(row: dict[str, object], field_name: str) -> str:
    value = row.get(field_name)
    return value if isinstance(value, str) else ""
