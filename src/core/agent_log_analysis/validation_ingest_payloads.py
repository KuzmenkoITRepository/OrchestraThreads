"""JSON payload normalization for ingest validation."""

from __future__ import annotations

from typing import Any

from core.agent_log_analysis.validation_json import validate_json_size


def normalize_metadata(
    payload: dict[str, Any],
    *,
    max_bytes: int,
) -> dict[str, Any]:
    """Validate metadata JSON payload size."""
    validate_json_size(payload, field_name="metadata", max_bytes=max_bytes)
    return dict(payload)


def normalize_raw_payload(
    payload: dict[str, Any] | None,
    *,
    max_bytes: int,
) -> dict[str, Any] | None:
    """Validate optional attached raw payload."""
    return normalize_optional_payload(
        payload,
        field_name="raw_payload",
        max_bytes=max_bytes,
    )


def normalize_optional_payload(
    payload: dict[str, Any] | None,
    *,
    field_name: str,
    max_bytes: int,
) -> dict[str, Any] | None:
    """Validate optional JSON payload under a byte limit."""
    if payload is None:
        return None
    validate_json_size(payload, field_name=field_name, max_bytes=max_bytes)
    return dict(payload)
