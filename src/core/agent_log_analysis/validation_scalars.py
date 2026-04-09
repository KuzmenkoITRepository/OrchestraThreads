"""Scalar validation helpers."""

from __future__ import annotations

from typing import Any

from core.agent_log_analysis.errors import ValidationError


def required_text(value: Any, *, field_name: str) -> str:
    """Return required stripped text or raise a validation error."""
    normalized = str(value or "").strip()
    if not normalized:
        raise ValidationError("VALIDATION_ERROR", f"{field_name} is required")
    return normalized


def optional_text(value: Any) -> str | None:
    """Return stripped text or ``None`` when empty."""
    normalized = str(value or "").strip()
    if normalized:
        return normalized
    return None


def bounded_text(value: Any, *, field_name: str, max_bytes: int) -> str:
    """Validate required text under byte limit."""
    normalized = required_text(value, field_name=field_name)
    if len(normalized.encode("utf-8")) > max_bytes:
        raise ValidationError(
            "VALIDATION_ERROR",
            f"{field_name} exceeds {max_bytes} bytes",
        )
    return normalized


def optional_bounded_text(
    value: Any,
    *,
    field_name: str,
    max_bytes: int,
) -> str | None:
    """Validate optional text under byte limit."""
    if value is None:
        return None
    return bounded_text(value, field_name=field_name, max_bytes=max_bytes)


def optional_int(value: Any, *, field_name: str) -> int | None:
    """Validate optional integer-like fields used by requests."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError("VALIDATION_ERROR", f"{field_name} must be an integer")
    return int(value)
