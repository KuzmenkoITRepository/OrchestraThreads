"""Tests for raw log store: insert, query, retention."""

from __future__ import annotations

import asyncio
import os
import unittest
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from core.agent_log_analysis.store import LogStore
from core.agent_log_analysis.store_raw_logs import RawLogQueryParams

_TEST_SCHEMA_PREFIX = "ala_rawlog_"
_WIDE_SINCE = datetime(2024, 1, 1, tzinfo=UTC)
_WIDE_UNTIL = datetime(2026, 1, 1, tzinfo=UTC)


def _database_url() -> str:
    return os.getenv(
        "AGENT_LOG_ANALYSIS_TEST_DATABASE_URL",
        os.getenv(
            "ORCHESTRA_THREADS_TEST_DATABASE_URL",
            "postgresql://orchestra:orchestra@127.0.0.1:5432/orchestra_threads",
        ),
    )


def _make_raw_row(
    agent_slug: str = "test-agent",
    occurred_at: datetime | None = None,
) -> dict[str, Any]:
    return {
        "event_id": None,
        "occurred_at": occurred_at or datetime(2025, 1, 1, tzinfo=UTC),
        "received_at": datetime(2025, 1, 1, 0, 0, 1, tzinfo=UTC),
        "agent_slug": agent_slug,
        "run_id": "run-1",
        "thread_id": None,
        "correlation_id": None,
        "source": "stdout",
        "level": "INFO",
        "raw_message": "test log message",
        "raw_payload_json": None,
    }


async def _seed_query_data(  # noqa: WPS476 - sequential inserts needed for ordered test data
    store: LogStore,
) -> None:
    base = datetime(2025, 1, 1, tzinfo=UTC)
    for idx in range(5):
        row = _make_raw_row(
            agent_slug="agent-a",
            occurred_at=base + timedelta(minutes=idx),
        )
        await store.insert_raw_log(row)  # noqa: WPS476
    other = _make_raw_row(agent_slug="agent-b")
    await store.insert_raw_log(other)


class TestRawLogInsert(unittest.TestCase):
    """Verify raw log insertion and log_id generation."""

    loop: asyncio.AbstractEventLoop
    test_schema: str
    store: LogStore

    @classmethod
    def setUpClass(cls) -> None:
        cls.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(cls.loop)
        cls.test_schema = _TEST_SCHEMA_PREFIX + uuid.uuid4().hex[:8]
        cls.store = LogStore(
            database_url=_database_url(),
            schema_name=cls.test_schema,
        )
        cls.loop.run_until_complete(cls.store.start())

    @classmethod
    def tearDownClass(cls) -> None:
        cls.loop.run_until_complete(cls.store.close())
        cls.loop.run_until_complete(cls.store.drop_schema())
        cls.loop.close()
        asyncio.set_event_loop(None)

    def test_insert_returns_log_id(self) -> None:
        log_id = self.loop.run_until_complete(self.store.insert_raw_log(_make_raw_row()))
        self.assertIsInstance(log_id, int)
        self.assertGreater(log_id, 0)

    def test_sequential_ids_increase(self) -> None:
        id1 = self.loop.run_until_complete(self.store.insert_raw_log(_make_raw_row()))
        id2 = self.loop.run_until_complete(self.store.insert_raw_log(_make_raw_row()))
        self.assertGreater(id2, id1)


class TestRawLogQueryIsolation(unittest.TestCase):
    """Verify agent-scoped query isolation."""

    loop: asyncio.AbstractEventLoop
    test_schema: str
    store: LogStore

    @classmethod
    def setUpClass(cls) -> None:
        cls.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(cls.loop)
        cls.test_schema = _TEST_SCHEMA_PREFIX + uuid.uuid4().hex[:8]
        cls.store = LogStore(
            database_url=_database_url(),
            schema_name=cls.test_schema,
        )
        cls.loop.run_until_complete(cls.store.start())
        cls.loop.run_until_complete(_seed_query_data(cls.store))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.loop.run_until_complete(cls.store.close())
        cls.loop.run_until_complete(cls.store.drop_schema())
        cls.loop.close()
        asyncio.set_event_loop(None)

    def test_agent_isolation(self) -> None:
        params = RawLogQueryParams(agent_slug="agent-a", since=_WIDE_SINCE, until=_WIDE_UNTIL)
        rows = self.loop.run_until_complete(self.store.query_raw_logs(params))
        self.assertEqual(len(rows), 5)

    def test_other_agent_not_returned(self) -> None:
        params = RawLogQueryParams(agent_slug="agent-a", since=_WIDE_SINCE, until=_WIDE_UNTIL)
        rows = self.loop.run_until_complete(self.store.query_raw_logs(params))
        slugs = {r["agent_slug"] for r in rows}
        self.assertEqual(slugs, {"agent-a"})


class TestRawLogQueryOrdering(unittest.TestCase):
    """Verify ordering and limit behavior."""

    loop: asyncio.AbstractEventLoop
    test_schema: str
    store: LogStore

    @classmethod
    def setUpClass(cls) -> None:
        cls.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(cls.loop)
        cls.test_schema = _TEST_SCHEMA_PREFIX + uuid.uuid4().hex[:8]
        cls.store = LogStore(
            database_url=_database_url(),
            schema_name=cls.test_schema,
        )
        cls.loop.run_until_complete(cls.store.start())
        cls.loop.run_until_complete(_seed_query_data(cls.store))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.loop.run_until_complete(cls.store.close())
        cls.loop.run_until_complete(cls.store.drop_schema())
        cls.loop.close()
        asyncio.set_event_loop(None)

    def test_ordering_desc(self) -> None:
        params = RawLogQueryParams(agent_slug="agent-a", since=_WIDE_SINCE, until=_WIDE_UNTIL)
        rows = self.loop.run_until_complete(self.store.query_raw_logs(params))
        timestamps = [r["occurred_at"] for r in rows]
        self.assertEqual(timestamps, sorted(timestamps, reverse=True))

    def test_limit(self) -> None:
        params = RawLogQueryParams(
            agent_slug="agent-a",
            since=_WIDE_SINCE,
            until=_WIDE_UNTIL,
            limit=2,
        )
        rows = self.loop.run_until_complete(self.store.query_raw_logs(params))
        self.assertEqual(len(rows), 2)


class TestRawLogRetention(unittest.TestCase):
    """Verify expired log deletion."""

    loop: asyncio.AbstractEventLoop
    test_schema: str
    store: LogStore

    @classmethod
    def setUpClass(cls) -> None:
        cls.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(cls.loop)
        cls.test_schema = _TEST_SCHEMA_PREFIX + uuid.uuid4().hex[:8]
        cls.store = LogStore(
            database_url=_database_url(),
            schema_name=cls.test_schema,
        )
        cls.loop.run_until_complete(cls.store.start())

    @classmethod
    def tearDownClass(cls) -> None:
        cls.loop.run_until_complete(cls.store.close())
        cls.loop.run_until_complete(cls.store.drop_schema())
        cls.loop.close()
        asyncio.set_event_loop(None)

    def test_delete_expired(self) -> None:
        old = _make_raw_row(occurred_at=datetime(2020, 1, 1, tzinfo=UTC))
        recent = _make_raw_row(occurred_at=datetime(2025, 6, 1, tzinfo=UTC))
        self.loop.run_until_complete(self.store.insert_raw_log(old))
        self.loop.run_until_complete(self.store.insert_raw_log(recent))
        cutoff = datetime(2024, 1, 1, tzinfo=UTC)
        deleted = self.loop.run_until_complete(self.store.delete_expired_raw_logs(cutoff))
        self.assertGreaterEqual(deleted, 1)
