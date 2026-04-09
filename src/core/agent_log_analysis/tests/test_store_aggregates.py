"""Tests for agent-scoped aggregation query store."""

from __future__ import annotations

import asyncio
import os
import unittest
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from core.agent_log_analysis.store import LogStore
from core.agent_log_analysis.store_aggregates import AggregateQueryParams

_TEST_SCHEMA_PREFIX = "ala_agg_"
_BASE_TIME = datetime(2025, 1, 1, tzinfo=UTC)
_WINDOW = timedelta(hours=1)
_SINCE = _BASE_TIME - _WINDOW
_UNTIL = _BASE_TIME + _WINDOW


def _database_url() -> str:
    return os.getenv(
        "AGENT_LOG_ANALYSIS_TEST_DATABASE_URL",
        os.getenv(
            "ORCHESTRA_THREADS_TEST_DATABASE_URL",
            "postgresql://orchestra:orchestra@127.0.0.1:5432/orchestra_threads",
        ),
    )


def _make_event_row(
    agent_slug: str = "agg-agent",
    status: str = "success",
    model_name: str = "gpt-4",
    latency_ms: int = 100,
) -> dict[str, Any]:
    return {
        "event_id": uuid.uuid4().hex,
        "event_type": "inference_event",
        "occurred_at": _BASE_TIME,
        "received_at": _BASE_TIME + timedelta(seconds=1),
        "agent_slug": agent_slug,
        "run_id": "run-1",
        "thread_id": None,
        "correlation_id": None,
        "parent_event_id": None,
        "status": status,
        "model_name": model_name,
        "provider_name": "openai",
        "request_kind": "chat",
        "action_kind": None,
        "target_name": None,
        "target_agent_slug": None,
        "latency_ms": latency_ms,
        "metadata_json": {},
        "payload_json": {"model": model_name},
        "raw_payload_attached": False,
    }


class TestAggregateValidation(unittest.TestCase):
    """Verify validation rejects invalid group keys and metrics."""

    loop: asyncio.AbstractEventLoop
    store: LogStore

    @classmethod
    def setUpClass(cls) -> None:
        cls.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(cls.loop)
        cls.store = LogStore(
            database_url=_database_url(),
            schema_name=_TEST_SCHEMA_PREFIX + uuid.uuid4().hex[:8],
        )
        cls.loop.run_until_complete(cls.store.start())

    @classmethod
    def tearDownClass(cls) -> None:
        cls.loop.run_until_complete(cls.store.close())
        cls.loop.run_until_complete(cls.store.drop_schema())
        cls.loop.close()
        asyncio.set_event_loop(None)

    def test_invalid_group_key_rejected(self) -> None:
        params = AggregateQueryParams(
            agent_slug="agg-agent",
            since=_SINCE,
            until=_UNTIL,
            group_by=["invalid_column"],
        )
        with self.assertRaises(ValueError):
            self.loop.run_until_complete(self.store.query_aggregates(params))

    def test_too_many_group_keys_rejected(self) -> None:
        params = AggregateQueryParams(
            agent_slug="agg-agent",
            since=_SINCE,
            until=_UNTIL,
            group_by=["status", "model_name", "provider_name", "event_type"],
        )
        with self.assertRaises(ValueError):
            self.loop.run_until_complete(self.store.query_aggregates(params))

    def test_invalid_metric_rejected(self) -> None:
        params = AggregateQueryParams(
            agent_slug="agg-agent",
            since=_SINCE,
            until=_UNTIL,
            metrics=["nonexistent_metric"],
        )
        with self.assertRaises(ValueError):
            self.loop.run_until_complete(self.store.query_aggregates(params))


class TestAggregateResults(unittest.TestCase):
    """Verify aggregation computation correctness."""

    loop: asyncio.AbstractEventLoop
    store: LogStore

    @classmethod
    def setUpClass(cls) -> None:
        cls.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(cls.loop)
        cls.store = LogStore(
            database_url=_database_url(),
            schema_name=_TEST_SCHEMA_PREFIX + uuid.uuid4().hex[:8],
        )
        cls.loop.run_until_complete(cls.store.start())
        cls.loop.run_until_complete(_seed_agg_data(cls.store))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.loop.run_until_complete(cls.store.close())
        cls.loop.run_until_complete(cls.store.drop_schema())
        cls.loop.close()
        asyncio.set_event_loop(None)

    def test_total_count(self) -> None:
        params = AggregateQueryParams(
            agent_slug="agg-agent",
            since=_SINCE,
            until=_UNTIL,
            metrics=["count"],
        )
        rows = self.loop.run_until_complete(self.store.query_aggregates(params))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["count"], 5)

    def test_group_by_status(self) -> None:
        params = AggregateQueryParams(
            agent_slug="agg-agent",
            since=_SINCE,
            until=_UNTIL,
            group_by=["status"],
            metrics=["count"],
        )
        rows = self.loop.run_until_complete(self.store.query_aggregates(params))
        by_status = {r["status"]: r["count"] for r in rows}
        self.assertEqual(by_status["success"], 3)
        self.assertEqual(by_status["error"], 2)

    def test_avg_latency(self) -> None:
        params = AggregateQueryParams(
            agent_slug="agg-agent",
            since=_SINCE,
            until=_UNTIL,
            metrics=["avg_latency_ms"],
        )
        rows = self.loop.run_until_complete(self.store.query_aggregates(params))
        self.assertIsNotNone(rows[0]["avg_latency_ms"])


async def _seed_agg_data(store: LogStore) -> None:  # noqa: WPS476
    for _ in range(3):
        row = _make_event_row(status="success", latency_ms=100)
        await store.insert_event(row, {})  # noqa: WPS476
    for _ in range(2):
        row = _make_event_row(status="error", latency_ms=200)
        await store.insert_event(row, {})  # noqa: WPS476
