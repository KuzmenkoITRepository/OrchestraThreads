"""JSON and mapping validation helpers."""

from __future__ import annotations

import json
from typing import Any

from core.agent_log_analysis.errors import ValidationError


def coerce_mapping(payload: Any, *, field_name: str) -> dict[str, Any]:
    """Validate that payload is a mapping and copy it."""
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValidationError("VALIDATION_ERROR", f"{field_name} must be an object")
    return dict(payload)


def coerce_optional_mapping(payload: Any, *, field_name: str) -> dict[str, Any] | None:
    """Return optional copied mapping."""
    if payload is None:
        return None
    return coerce_mapping(payload, field_name=field_name)


def validate_json_size(
    payload: dict[str, Any],
    *,
    field_name: str,
    max_bytes: int,
) -> None:
    """Ensure a mapping is JSON-serializable and under the byte limit."""
    try:
        raw_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    except TypeError as err:
        raise ValidationError(
            "VALIDATION_ERROR",
            f"{field_name} must be JSON-serializable",
        ) from err
    raw_size = len(raw_json.encode("utf-8"))
    if raw_size > max_bytes:
        raise ValidationError(
            "VALIDATION_ERROR",
            f"{field_name} exceeds {max_bytes} bytes",
        )
