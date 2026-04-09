"""Row normalization helpers for asyncpg result mapping."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast


def parse_timestamp(raw_value: Any) -> datetime | None:
    """Parse a raw value into a UTC-normalized datetime."""
    if raw_value is None:
        return None
    if isinstance(raw_value, datetime):
        return _normalize_datetime(raw_value)
    normalized = str(raw_value).strip()
    if not normalized:
        return None
    parsed = datetime.fromisoformat(normalized)
    return _normalize_datetime(parsed)


def normalize_value(raw_value: Any) -> Any:
    """Normalize a single database value for JSON serialization."""
    if isinstance(raw_value, datetime):
        parsed = parse_timestamp(raw_value)
        if parsed is not None:
            return parsed.isoformat()
        return raw_value.isoformat()
    return raw_value


def row_to_dict(row: Any) -> dict[str, Any] | None:
    """Convert an asyncpg Record to a normalized dict."""
    if row is None:
        return None
    payload = dict(row)
    for key, raw_value in list(payload.items()):
        normalized = normalize_value(raw_value)
        payload[key] = normalized
        if isinstance(normalized, str) and key.endswith("_json"):
            parsed_json = _parse_json_text(normalized)
            if parsed_json is not None:
                payload[key] = parsed_json
    return payload


def _normalize_datetime(raw_value: datetime) -> datetime:
    if raw_value.tzinfo is None:
        return raw_value.replace(tzinfo=UTC)
    return raw_value.astimezone(UTC)


def _parse_json_text(normalized: str) -> object | None:
    try:
        return cast(object, json.loads(normalized))
    except json.JSONDecodeError:
        return None
