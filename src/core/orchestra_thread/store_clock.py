from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any


def timestamp_within_lease(raw_value: Any, *, lease_seconds: int) -> bool:
    parsed = _parse_timestamp(raw_value)
    if parsed is None:
        return False
    return datetime.now(UTC) - parsed <= timedelta(seconds=lease_seconds)


def _parse_timestamp(raw_value: Any) -> datetime | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, datetime):
        if raw_value.tzinfo is None:
            return raw_value.replace(tzinfo=UTC)
        return raw_value.astimezone(UTC)
    normalized = str(raw_value).strip()
    if normalized:
        return datetime.fromisoformat(normalized)
    return None
