"""Tests for bounded correlation chain lookup store."""

from __future__ import annotations

import asyncio
import os
import unittest
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from core.agent_log_analysis.store import LogStore
from core.agent_log_analysis.store_correlation import CorrelationQueryParams

_TEST_SCHEMA_PREFIX = "ala_corr_"
_BASE_TIME = datetime(2025, 1, 1, tzinfo=UTC)


def _database_url() -> str:
    return os.getenv(
        "AGENT_LOG_ANALYSIS_TEST_DATABASE_URL",
        os.getenv(
            "ORCHESTRA_THREADS_TEST_DATABASE_URL",
            "postgresql://orchestra:orchestra@127.0.0.1:5432/orchestra_threads",
        ),
    )


def _make_event_row(
    agent_slug: str = "corr-agent",
    occurred_at: datetime | None = None,
    correlation_id: str = "chain-1",
) -> dict[str, Any]:
    return {
        "event_id": uuid.uuid4().hex,
        "event_type": "inference_event",
        "occurred_at": occurred_at or _BASE_TIME,
        "received_at": _BASE_TIME + timedelta(seconds=1),
        "agent_slug": agent_slug,
        "run_id": "run-1",
        "thread_id": None,
        "correlation_id": correlation_id,
        "parent_event_id": None,
        "status": "success",
        "model_name": "gpt-4",
        "provider_name": "openai",
        "request_kind": "chat",
        "action_kind": None,
        "target_name": None,
        "target_agent_slug": None,
        "latency_ms": 100,
        "metadata_json": {},
        "payload_json": {"model": "gpt-4"},
        "raw_payload_attached": False,
    }


class TestCorrelationChain(unittest.TestCase):
    """Verify bounded correlation chain retrieval."""

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
        cls.loop.run_until_complete(_seed_chain_data(cls.store))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.loop.run_until_complete(cls.store.close())
        cls.loop.run_until_complete(cls.store.drop_schema())
        cls.loop.close()
        asyncio.set_event_loop(None)

    def test_chain_returned(self) -> None:
        params = CorrelationQueryParams(
            agent_slug="corr-agent",
            correlation_id="chain-1",
        )
        chain = self.loop.run_until_complete(
            self.store.query_correlation_chain(params),
        )
        self.assertEqual(len(chain), 5)

    def test_asc_ordering(self) -> None:
        params = CorrelationQueryParams(
            agent_slug="corr-agent",
            correlation_id="chain-1",
        )
        chain = self.loop.run_until_complete(
            self.store.query_correlation_chain(params),
        )
        timestamps = [r["occurred_at"] for r in chain]
        self.assertEqual(timestamps, sorted(timestamps))


class TestCorrelationIsolation(unittest.TestCase):
    """Verify agent isolation and max_nodes cap."""

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
        cls.loop.run_until_complete(_seed_isolation_data(cls.store))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.loop.run_until_complete(cls.store.close())
        cls.loop.run_until_complete(cls.store.drop_schema())
        cls.loop.close()
        asyncio.set_event_loop(None)

    def test_agent_scoped(self) -> None:
        params = CorrelationQueryParams(
            agent_slug="corr-agent-a",
            correlation_id="shared-corr",
        )
        chain = self.loop.run_until_complete(
            self.store.query_correlation_chain(params),
        )
        slugs = {r["agent_slug"] for r in chain}
        self.assertEqual(slugs, {"corr-agent-a"})

    def test_max_nodes_cap(self) -> None:
        params = CorrelationQueryParams(
            agent_slug="corr-agent-a",
            correlation_id="shared-corr",
            max_nodes=2,
        )
        chain = self.loop.run_until_complete(
            self.store.query_correlation_chain(params),
        )
        self.assertLessEqual(len(chain), 2)


async def _seed_chain_data(store: LogStore) -> None:  # noqa: WPS476
    for idx in range(5):
        row = _make_event_row(
            occurred_at=_BASE_TIME + timedelta(minutes=idx),
        )
        await store.insert_event(row, {})  # noqa: WPS476


async def _seed_isolation_data(store: LogStore) -> None:  # noqa: WPS476
    for idx in range(3):
        row = _make_event_row(
            agent_slug="corr-agent-a",
            occurred_at=_BASE_TIME + timedelta(minutes=idx),
            correlation_id="shared-corr",
        )
        await store.insert_event(row, {})  # noqa: WPS476
    for idx in range(2):
        row = _make_event_row(
            agent_slug="corr-agent-b",
            occurred_at=_BASE_TIME + timedelta(minutes=idx),
            correlation_id="shared-corr",
        )
        await store.insert_event(row, {})  # noqa: WPS476
