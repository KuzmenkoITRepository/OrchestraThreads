"""Agent-scoped aggregation query store."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.agent_log_analysis.common import MAX_AGGREGATE_GROUP_KEYS
from core.agent_log_analysis.store_protocols import StorePoolProtocol

_ALLOWED_GROUP_KEYS = frozenset(
    (
        "event_type",
        "status",
        "request_kind",
        "action_kind",
        "provider_name",
        "model_name",
        "target_name",
        "target_agent_slug",
    )
)

_ALLOWED_METRICS = frozenset(
    (
        "count",
        "success_count",
        "error_count",
        "avg_latency_ms",
    )
)


@dataclass(frozen=True)
class AggregateQueryParams:
    """Typed parameters for aggregation queries."""

    agent_slug: str
    since: datetime
    until: datetime
    group_by: list[str] = field(default_factory=list)
    metrics: list[str] = field(default_factory=list)


class AggregateStoreMixin:
    """Mixin for bounded aggregation queries."""

    pool: StorePoolProtocol | None

    async def query_aggregates(
        self,
        params: AggregateQueryParams,
    ) -> list[dict[str, Any]]:
        """Run an agent-scoped aggregation query.

        Validates group_by keys and metrics before execution.
        Raises ValueError for invalid group keys or metrics.
        """
        assert self.pool is not None
        _validate_params(params)
        sql, values = _build_aggregate_sql(params)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, *values)
        return [dict(r) for r in rows]


def _validate_params(params: AggregateQueryParams) -> None:
    if len(params.group_by) > MAX_AGGREGATE_GROUP_KEYS:
        raise ValueError(
            f"Too many group keys: {len(params.group_by)}, max {MAX_AGGREGATE_GROUP_KEYS}",
        )
    bad_keys = set(params.group_by) - _ALLOWED_GROUP_KEYS
    if bad_keys:
        raise ValueError(f"Invalid group keys: {sorted(bad_keys)}")
    bad_metrics = set(params.metrics) - _ALLOWED_METRICS
    if bad_metrics:
        raise ValueError(f"Invalid metrics: {sorted(bad_metrics)}")


def _build_aggregate_sql(
    params: AggregateQueryParams,
) -> tuple[str, list[Any]]:
    select_cols = _build_select_cols(params)
    values: list[Any] = [params.agent_slug, params.since, params.until]
    tail = ""
    if params.group_by:
        joined = ", ".join(params.group_by)
        tail = f" GROUP BY {joined} ORDER BY {joined}"
    sql = (
        f"SELECT {select_cols} FROM agent_log_events"  # noqa: S608 - parameterized
        f" WHERE agent_slug = $1 AND occurred_at >= $2 AND occurred_at <= $3{tail}"
    )
    return sql, values


def _build_select_cols(params: AggregateQueryParams) -> str:
    parts: list[str] = list(params.group_by)
    parts.append("COUNT(*) AS count")
    effective = params.metrics or list(_ALLOWED_METRICS)
    if "success_count" in effective:
        parts.append(
            "COUNT(*) FILTER (WHERE status = 'success') AS success_count",
        )
    if "error_count" in effective:
        parts.append(
            "COUNT(*) FILTER (WHERE status = 'error') AS error_count",
        )
    if "avg_latency_ms" in effective:
        parts.append("AVG(latency_ms) AS avg_latency_ms")
    return ", ".join(parts)
