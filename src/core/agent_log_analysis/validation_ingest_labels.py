"""Label normalization for ingest validation."""

from __future__ import annotations

from typing import Any

from core.agent_log_analysis.common import (
    MAX_LABEL_KEY_LENGTH,
    MAX_LABEL_VALUE_LENGTH,
)
from core.agent_log_analysis.errors import ValidationError
from core.agent_log_analysis.validation_scalars import required_text


def normalize_labels(payload: dict[str, Any], *, max_labels: int) -> dict[str, str]:
    """Validate labels count, keys, and values."""
    if len(payload) > max_labels:
        raise ValidationError(
            "VALIDATION_ERROR",
            f"labels must not exceed {max_labels} items",
        )
    result: dict[str, str] = {}
    for raw_key, raw_value in payload.items():
        key = required_text(raw_key, field_name="labels key")
        value = required_text(raw_value, field_name=f"labels[{key}]")
        _validate_label_lengths(key, value)
        result[key] = value
    return result


def _validate_label_lengths(key: str, value: str) -> None:
    if len(key) > MAX_LABEL_KEY_LENGTH:
        raise ValidationError(
            "VALIDATION_ERROR",
            f"labels key exceeds {MAX_LABEL_KEY_LENGTH} characters",
        )
    if len(value) > MAX_LABEL_VALUE_LENGTH:
        raise ValidationError(
            "VALIDATION_ERROR",
            f"labels[{key}] exceeds {MAX_LABEL_VALUE_LENGTH} characters",
        )
