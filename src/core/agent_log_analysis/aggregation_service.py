"""Aggregation service over validated store queries."""

from __future__ import annotations

from typing import Protocol

from core.agent_log_analysis.api_response_models import (
    AggregationBucket,
    AggregationResult,
)
from core.agent_log_analysis.store_aggregates import AggregateQueryParams
from core.agent_log_analysis.validation_time import serialize_timestamp


class _AggregateStoreProtocol(Protocol):
    async def query_aggregates(
        self,
        params: AggregateQueryParams,
    ) -> list[dict[str, object]]: ...


class AggregationService:
    """Build typed aggregation responses from store rows."""

    def __init__(self, *, store: _AggregateStoreProtocol) -> None:
        self._store = store

    async def aggregate_agent_events(
        self,
        params: AggregateQueryParams,
    ) -> AggregationResult:
        rows = await self._store.query_aggregates(params)
        return AggregationResult(
            agent_slug=params.agent_slug,
            window_start=serialize_timestamp(params.since),
            window_end=serialize_timestamp(params.until),
            group_by=list(params.group_by),
            metrics=_effective_metrics(params),
            buckets=[_map_bucket(row, group_by=params.group_by) for row in rows],
        )


def _effective_metrics(params: AggregateQueryParams) -> list[str]:
    if params.metrics:
        return list(params.metrics)
    return ["count", "success_count", "error_count", "avg_latency_ms"]


def _map_bucket(
    row: dict[str, object],
    *,
    group_by: list[str],
) -> AggregationBucket:
    return AggregationBucket(
        keys=_bucket_keys(row, group_by=group_by),
        count=_row_int(row, "count"),
        success_count=_row_int(row, "success_count"),
        error_count=_row_int(row, "error_count"),
        avg_latency_ms=_row_float(row, "avg_latency_ms"),
    )


def _bucket_keys(
    row: dict[str, object],
    *,
    group_by: list[str],
) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for key in group_by:
        value = row.get(key)
        result[key] = value if isinstance(value, str) else None
    return result


def _row_int(row: dict[str, object], field_name: str) -> int:
    value = row.get(field_name)
    return value if isinstance(value, int) else 0


def _row_float(row: dict[str, object], field_name: str) -> float | None:
    value = row.get(field_name)
    if isinstance(value, int | float):
        return float(value)
    return None
