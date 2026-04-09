"""Timestamp parsing and serialization helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from core.agent_log_analysis.errors import ValidationError
from core.agent_log_analysis.validation_scalars import required_text


def parse_timestamp(value: Any, *, field_name: str) -> datetime:
    """Parse an ISO-8601 timestamp with timezone into UTC."""
    raw_value = required_text(value, field_name=field_name)
    normalized = raw_value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as err:
        raise ValidationError(
            "VALIDATION_ERROR",
            f"{field_name} must be an ISO-8601 timestamp",
        ) from err
    if parsed.tzinfo is None:
        raise ValidationError(
            "VALIDATION_ERROR",
            f"{field_name} must include timezone",
        )
    return parsed.astimezone(UTC)


def serialize_timestamp(value: datetime) -> str:
    """Serialize a UTC timestamp to a stable Zulu string."""
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
