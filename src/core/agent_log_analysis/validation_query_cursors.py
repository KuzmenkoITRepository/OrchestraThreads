"""Cursor parsing for analytical queries."""

from __future__ import annotations

from datetime import datetime

from core.agent_log_analysis.errors import ValidationError
from core.agent_log_analysis.validation_time import parse_timestamp


def parse_event_cursor(cursor: str | None) -> tuple[datetime | None, str | None]:
    """Parse `(occurred_at, event_id)` cursor."""
    if cursor is None:
        return None, None
    occurred_at, separator, event_id = cursor.partition("|")
    if separator and event_id.strip():
        return parse_timestamp(occurred_at, field_name="cursor timestamp"), event_id.strip()
    raise ValidationError("VALIDATION_ERROR", "event cursor is invalid")


def parse_raw_log_cursor(cursor: str | None) -> tuple[datetime | None, int | None]:
    """Parse `(occurred_at, log_id)` raw-log cursor."""
    if cursor is None:
        return None, None
    occurred_at, separator, raw_id = cursor.partition("|")
    if not separator or not raw_id.strip():
        raise ValidationError("VALIDATION_ERROR", "raw log cursor is invalid")
    try:
        log_id = int(raw_id)
    except ValueError as err:
        raise ValidationError("VALIDATION_ERROR", "raw log cursor is invalid") from err
    return parse_timestamp(occurred_at, field_name="cursor timestamp"), log_id
