"""Query filter and grouping normalization."""

from __future__ import annotations

from typing import Any

from core.agent_log_analysis.errors import ValidationError
from core.agent_log_analysis.raw_log_models import RawLogLevel
from core.agent_log_analysis.store_aggregates import (
    _ALLOWED_GROUP_KEYS,
    _ALLOWED_METRICS,
)
from core.agent_log_analysis.store_query_sql import _ALLOWED_FILTERS


def build_event_filters(request: Any) -> dict[str, str]:
    """Normalize supported event-query filters."""
    filters = _compact_filters(
        run_id=request.run_id,
        thread_id=request.thread_id,
        correlation_id=request.correlation_id,
        event_type=request.event_type,
        status=request.status,
        request_kind=request.request_kind,
        action_kind=request.action_kind,
        target_name=request.target_name,
        target_agent_slug=request.target_agent_slug,
        provider_name=request.provider_name,
        model_name=request.model_name,
    )
    invalid_keys = set(filters) - _ALLOWED_FILTERS
    if not invalid_keys:
        return filters
    raise ValidationError(
        "VALIDATION_ERROR",
        f"invalid filters: {sorted(invalid_keys)}",
    )


def build_timeline_filters(*, run_id: str | None, thread_id: str | None) -> dict[str, str]:
    """Normalize timeline filters."""
    return _compact_filters(run_id=run_id, thread_id=thread_id)


def normalize_labels(labels: dict[str, str]) -> dict[str, str]:
    """Trim query label filters."""
    return {key.strip(): value.strip() for key, value in labels.items()}


def normalize_group_by(group_by: list[str], *, max_group_keys: int) -> list[str]:
    """Validate aggregation grouping keys."""
    if len(group_by) > max_group_keys:
        raise ValidationError(
            "TOO_MANY_GROUP_KEYS",
            f"group_by must not exceed {max_group_keys} keys",
        )
    invalid = set(group_by) - _ALLOWED_GROUP_KEYS
    if not invalid:
        return list(group_by)
    raise ValidationError(
        "INVALID_GROUP_BY",
        f"group_by contains invalid keys: {sorted(invalid)}",
    )


def normalize_metrics(metrics: list[str]) -> list[str]:
    """Validate aggregation metric names."""
    invalid = set(metrics) - _ALLOWED_METRICS
    if not invalid:
        return list(metrics)
    raise ValidationError(
        "VALIDATION_ERROR",
        f"metrics contains invalid values: {sorted(invalid)}",
    )


def parse_optional_level(value: str | None) -> RawLogLevel | None:
    """Parse optional raw-log level filter."""
    if value is None:
        return None
    try:
        return RawLogLevel(value)
    except ValueError as err:
        raise ValidationError("VALIDATION_ERROR", "level is invalid") from err


def _compact_filters(**kwargs: str | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in kwargs.items():
        if value is not None and value.strip():
            result[key] = value
    return result
