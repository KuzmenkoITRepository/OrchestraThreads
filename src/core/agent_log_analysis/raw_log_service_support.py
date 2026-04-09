"""Mapping helpers for raw log service."""

from __future__ import annotations

from datetime import datetime

from core.agent_log_analysis.raw_log_models import RawLogLevel, RawLogRecord
from core.agent_log_analysis.validation_time import parse_timestamp


def map_raw_log(row: dict[str, object]) -> RawLogRecord:
    """Map a raw-log row into the public DTO."""
    return RawLogRecord(
        log_id=_required_int(row, "log_id"),
        event_id=_optional_text(row.get("event_id")),
        occurred_at=_timestamp(row.get("occurred_at"), field_name="occurred_at"),
        received_at=_timestamp(row.get("received_at"), field_name="received_at"),
        agent_slug=_required_text(row, "agent_slug"),
        run_id=_optional_text(row.get("run_id")),
        thread_id=_optional_text(row.get("thread_id")),
        correlation_id=_optional_text(row.get("correlation_id")),
        source=_optional_text(row.get("source")),
        level=_level_value(row),
        raw_message=_required_text(row, "raw_message"),
        raw_payload_json=_payload_value(row.get("raw_payload_json")),
    )


def _timestamp(value: object, *, field_name: str) -> datetime:
    if isinstance(value, datetime):
        return value
    return parse_timestamp(value, field_name=field_name)


def _required_text(row: dict[str, object], field_name: str) -> str:
    value = row.get(field_name)
    return value if isinstance(value, str) else ""


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _payload_value(value: object) -> dict[str, object] | None:
    return dict(value) if isinstance(value, dict) else None


def _required_int(row: dict[str, object], field_name: str) -> int:
    value = row.get(field_name)
    return int(value) if isinstance(value, int) else 0


def _level_value(row: dict[str, object]) -> RawLogLevel:
    return RawLogLevel(_required_text(row, "level"))
