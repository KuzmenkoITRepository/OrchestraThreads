"""SQL query building and typed params for agent-scoped event queries."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class EventQueryParams:
    """Typed parameters for agent-scoped event queries."""

    agent_slug: str
    since: datetime
    until: datetime
    limit: int = 50
    cursor_occurred_at: datetime | None = None
    cursor_event_id: str | None = None
    filters: dict[str, str] = field(default_factory=dict)
    label_filters: dict[str, str] = field(default_factory=dict)


_ALLOWED_FILTERS = frozenset(
    (
        "run_id",
        "thread_id",
        "correlation_id",
        "event_type",
        "status",
        "request_kind",
        "action_kind",
        "target_name",
        "target_agent_slug",
        "provider_name",
        "model_name",
    )
)


def build_event_query(
    params: EventQueryParams,
) -> tuple[str, list[Any]]:
    """Build parameterized SQL for agent-scoped event queries."""
    clauses = ["e.agent_slug = $1", "e.occurred_at >= $2", "e.occurred_at <= $3"]
    values: list[Any] = [params.agent_slug, params.since, params.until]
    idx = _append_cursor(clauses, values, 4, params)
    idx = _append_column_filters(clauses, values, idx, params.filters)
    join_sql = _apply_labels(values, idx, params.label_filters)
    return _finalize_sql(clauses, values, join_sql, params.limit)


def _finalize_sql(
    clauses: list[str],
    values: list[Any],
    join_sql: str,
    limit: int,
) -> tuple[str, list[Any]]:
    where = " AND ".join(clauses)
    limit_idx = len(values) + 1
    sql = (
        f"SELECT e.* FROM agent_log_events e{join_sql}"  # noqa: S608
        f" WHERE {where}"
        f" ORDER BY e.occurred_at DESC, e.event_id DESC LIMIT ${limit_idx}"
    )
    values.append(limit)
    return sql, values


def _append_cursor(
    clauses: list[str],
    values: list[Any],
    idx: int,
    params: EventQueryParams,
) -> int:
    if params.cursor_occurred_at is not None and params.cursor_event_id is not None:
        clauses.append(f"(e.occurred_at, e.event_id) < (${idx}, ${idx + 1})")
        values.extend([params.cursor_occurred_at, params.cursor_event_id])
        idx += 2
    return idx


def _append_column_filters(
    clauses: list[str],
    values: list[Any],
    idx: int,
    filters: dict[str, str],
) -> int:
    for col, col_value in filters.items():
        if col in _ALLOWED_FILTERS:
            clauses.append(f"e.{col} = ${idx}")
            values.append(col_value)
            idx += 1
    return idx


def _apply_labels(
    values: list[Any],
    idx: int,
    label_filters: dict[str, str],
) -> str:
    if not label_filters:
        return ""
    parts: list[str] = []
    for label_idx, (lkey, lval) in enumerate(label_filters.items()):
        parts.append(
            f" JOIN agent_log_event_labels lbl{label_idx}"
            f" ON lbl{label_idx}.event_id = e.event_id"
            f" AND lbl{label_idx}.label_key = ${idx}"
            f" AND lbl{label_idx}.label_value = ${idx + 1}",
        )
        values.extend([lkey, lval])
        idx += 2
    return "".join(parts)
