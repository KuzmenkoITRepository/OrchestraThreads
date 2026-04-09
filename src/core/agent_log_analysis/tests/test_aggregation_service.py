"""Tests for aggregation service behavior."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from importlib import import_module
from typing import Protocol, cast

from core.agent_log_analysis.api_response_models import AggregationResult
from core.agent_log_analysis.store_aggregates import AggregateQueryParams

_BASE_TIME = datetime(2025, 1, 1, tzinfo=UTC)
_WINDOW = timedelta(hours=1)


class TestAggregationService(unittest.IsolatedAsyncioTestCase):
    """Verify aggregation result shaping."""

    async def test_returns_typed_result(self) -> None:
        store = _FakeAggregateStore(rows=[_row(status="success")])
        result = await _service(store).aggregate_agent_events(_params())
        _assert_result_shape(self, result)
        self.assertEqual(store.calls, [_params()])

    async def test_fills_missing_group_keys_with_none(self) -> None:
        store = _FakeAggregateStore(rows=[_row(model_name=None)])
        result = await _service(store).aggregate_agent_events(_params())
        self.assertEqual(
            result.buckets[0].keys,
            {"status": "success", "model_name": None},
        )

    async def test_returns_empty_result(self) -> None:
        result = await _service(_FakeAggregateStore()).aggregate_agent_events(_params())
        self.assertEqual(result.agent_slug, "agent-a")
        self.assertEqual(result.metrics, ["count", "avg_latency_ms"])
        self.assertEqual(result.buckets, [])

    async def test_limits_metrics_to_approved_fields(self) -> None:
        store = _FakeAggregateStore(
            rows=[_row(success_count=1, error_count=0, avg_latency_ms=None)]
        )
        result = await _service(store).aggregate_agent_events(
            _params(metrics=["count", "success_count", "error_count", "avg_latency_ms"]),
        )
        bucket = result.buckets[0]
        self.assertEqual(bucket.count, 2)
        self.assertEqual(bucket.success_count, 1)
        self.assertEqual(bucket.error_count, 0)
        self.assertIsNone(bucket.avg_latency_ms)


class _FakeAggregateStore:
    def __init__(self, *, rows: list[dict[str, object]] | None = None) -> None:
        self._rows = rows or []
        self.calls: list[AggregateQueryParams] = []

    async def query_aggregates(self, params: AggregateQueryParams) -> list[dict[str, object]]:
        self.calls.append(params)
        return list(self._rows)


class _AggregationServiceProtocol(Protocol):
    def __init__(self, *, store: _FakeAggregateStore) -> None: ...

    async def aggregate_agent_events(self, params: AggregateQueryParams) -> AggregationResult: ...


def _params(*, metrics: list[str] | None = None) -> AggregateQueryParams:
    return AggregateQueryParams(
        agent_slug="agent-a",
        since=_BASE_TIME - _WINDOW,
        until=_BASE_TIME + _WINDOW,
        group_by=["status", "model_name"],
        metrics=metrics or ["count", "avg_latency_ms"],
    )


def _service(store: _FakeAggregateStore) -> _AggregationServiceProtocol:
    service_module = import_module("core.agent_log_analysis.aggregation_service")
    service_cls = cast(type[_AggregationServiceProtocol], service_module.AggregationService)
    return service_cls(store=store)


def _row(**overrides: object) -> dict[str, object]:
    row = {
        "status": "success",
        "model_name": "gpt-4o",
        "count": 2,
        "success_count": 0,
        "error_count": 0,
        "avg_latency_ms": 123.5,
    }
    row.update(overrides)
    return row


def _assert_result_shape(
    case: unittest.TestCase,
    result: AggregationResult,
) -> None:
    case.assertEqual(result.agent_slug, "agent-a")
    case.assertEqual(result.window_start, "2024-12-31T23:00:00Z")
    case.assertEqual(result.window_end, "2025-01-01T01:00:00Z")
    case.assertEqual(result.group_by, ["status", "model_name"])
    case.assertEqual(result.metrics, ["count", "avg_latency_ms"])
    case.assertEqual(len(result.buckets), 1)
    case.assertEqual(result.buckets[0].keys, {"status": "success", "model_name": "gpt-4o"})
    case.assertEqual(result.buckets[0].count, 2)
    case.assertEqual(result.buckets[0].avg_latency_ms, 123.5)
