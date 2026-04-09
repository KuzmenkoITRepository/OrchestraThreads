"""Raw-log row builders for validated ingest requests."""

from __future__ import annotations

from datetime import datetime

from core.agent_log_analysis.api_models import IngestEventRequest
from core.agent_log_analysis.validation_time import parse_timestamp


def build_raw_log_rows(
    request: IngestEventRequest,
    *,
    received_at: datetime,
) -> list[dict[str, object]]:
    """Build all raw-log rows for one event."""
    return [_build_raw_log_row(raw_log, received_at=received_at) for raw_log in request.raw_logs]


def _build_raw_log_row(
    raw_log: dict[str, object],
    *,
    received_at: datetime,
) -> dict[str, object]:
    return {
        "event_id": raw_log.get("event_id"),
        "occurred_at": parse_timestamp(
            raw_log.get("occurred_at"),
            field_name="raw_logs[].occurred_at",
        ),
        "received_at": received_at,
        "agent_slug": raw_log.get("agent_slug"),
        "run_id": raw_log.get("run_id"),
        "thread_id": raw_log.get("thread_id"),
        "correlation_id": raw_log.get("correlation_id"),
        "source": raw_log.get("source"),
        "level": raw_log.get("level"),
        "raw_message": raw_log.get("raw_message"),
        "raw_payload_json": raw_log.get("raw_payload_json"),
    }
