"""Query bounds, cursors, and scope helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from core.agent_log_analysis.errors import ValidationError
from core.agent_log_analysis.validation_scalars import optional_text
from core.agent_log_analysis.validation_time import parse_timestamp


def require_agent_slug(value: str) -> str:
    """Require analytical `agent_slug` scope."""
    normalized = optional_text(value)
    if normalized is not None:
        return normalized
    raise ValidationError(
        "AGENT_SCOPE_REQUIRED",
        "agent_slug is required for analytical queries",
    )


def resolve_limit(limit: int | None, *, default_limit: int, max_limit: int) -> int:
    """Resolve effective limit under configured bounds."""
    effective = default_limit if limit is None else limit
    if effective <= 0:
        raise ValidationError("VALIDATION_ERROR", "limit must be positive")
    if effective <= max_limit:
        return effective
    raise ValidationError(
        "PAGE_LIMIT_TOO_LARGE",
        f"limit must not exceed {max_limit}",
    )


def resolve_window(
    window_start: str | None,
    window_end: str | None,
    *,
    query_window_hours: int,
) -> tuple[datetime, datetime]:
    """Resolve and validate analytical time window."""
    until = _resolve_window_end(window_end)
    since = _resolve_window_start(
        window_start,
        until=until,
        query_window_hours=query_window_hours,
    )
    _validate_window_order(since=since, until=until)
    _validate_window_size(
        since=since,
        until=until,
        query_window_hours=query_window_hours,
    )
    return since, until


def _resolve_window_end(window_end: str | None) -> datetime:
    if window_end is None:
        return datetime.now(tz=UTC)
    return parse_timestamp(window_end, field_name="window_end")


def _resolve_window_start(
    window_start: str | None,
    *,
    until: datetime,
    query_window_hours: int,
) -> datetime:
    if window_start is None:
        return until - timedelta(hours=query_window_hours)
    return parse_timestamp(window_start, field_name="window_start")


def _validate_window_order(*, since: datetime, until: datetime) -> None:
    if since > until:
        raise ValidationError("VALIDATION_ERROR", "window_start must be before window_end")


def _validate_window_size(
    *,
    since: datetime,
    until: datetime,
    query_window_hours: int,
) -> None:
    window = until - since
    max_window = timedelta(hours=query_window_hours)
    if window > max_window:
        raise ValidationError(
            "QUERY_WINDOW_TOO_LARGE",
            f"query window must not exceed {query_window_hours} hours",
        )
