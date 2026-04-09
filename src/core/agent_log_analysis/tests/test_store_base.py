"""Tests for store base layer: pool lifecycle, schema bootstrap, helpers."""

from __future__ import annotations

import asyncio
import os
import unittest
import uuid
from typing import Any

from core.agent_log_analysis.store_base import LogStoreBase
from core.agent_log_analysis.store_row_helpers import (
    normalize_value,
    parse_timestamp,
    row_to_dict,
)

_TEST_SCHEMA_PREFIX = "ala_base_"

_EXPECTED_TABLES = (
    "agent_log_events",
    "agent_log_event_labels",
    "agent_log_raw_logs",
)

_EXPECTED_INDEXES = (
    "agent_log_events_agent_time_idx",
    "agent_log_events_corr_idx",
    "agent_log_events_run_idx",
    "agent_log_events_thread_idx",
    "agent_log_events_status_idx",
    "agent_log_event_labels_lookup_idx",
    "agent_log_raw_logs_agent_time_idx",
    "agent_log_raw_logs_corr_idx",
)


def _database_url() -> str:
    return os.getenv(
        "AGENT_LOG_ANALYSIS_TEST_DATABASE_URL",
        os.getenv(
            "ORCHESTRA_THREADS_TEST_DATABASE_URL",
            "postgresql://orchestra:orchestra@127.0.0.1:5432/orchestra_threads",
        ),
    )


class TestStoreBaseInit(unittest.TestCase):
    """Validate constructor guards."""

    def test_empty_url_raises(self) -> None:
        with self.assertRaises(ValueError):
            LogStoreBase(database_url="")

    def test_whitespace_url_raises(self) -> None:
        with self.assertRaises(ValueError):
            LogStoreBase(database_url="   ")

    def test_invalid_schema_raises(self) -> None:
        with self.assertRaises(ValueError):
            LogStoreBase(database_url="postgresql://x", schema_name="bad-name!")

    def test_default_schema(self) -> None:
        store = LogStoreBase(database_url="postgresql://x")
        self.assertEqual(store.schema_name, "agent_log_analysis")

    def test_pool_size_clamp(self) -> None:
        store = LogStoreBase(
            database_url="postgresql://x",
            min_pool_size=0,
            max_pool_size=0,
        )
        self.assertGreaterEqual(store.min_pool_size, 1)
        self.assertGreaterEqual(store.max_pool_size, store.min_pool_size)


class TestStoreBaseSchemaBootstrap(unittest.TestCase):
    """Verify schema creation, table presence, and index presence."""

    loop: asyncio.AbstractEventLoop
    test_schema: str
    store: LogStoreBase

    @classmethod
    def setUpClass(cls) -> None:
        cls.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(cls.loop)
        cls.test_schema = _TEST_SCHEMA_PREFIX + uuid.uuid4().hex[:8]
        cls.store = LogStoreBase(
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

    def test_ping(self) -> None:
        result = self.loop.run_until_complete(self.store.ping())
        self.assertTrue(result)

    def test_tables_exist(self) -> None:
        tables = self.loop.run_until_complete(self._fetch_tables())
        for expected in _EXPECTED_TABLES:
            self.assertIn(expected, tables)

    def test_indexes_exist(self) -> None:
        indexes = self.loop.run_until_complete(self._fetch_indexes())
        for expected in _EXPECTED_INDEXES:
            self.assertIn(expected, indexes, f"Missing index: {expected}")

    async def _fetch_tables(self) -> list[str]:
        assert self.store.pool is not None
        async with self.store.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT tablename FROM pg_tables WHERE schemaname = $1",
                self.test_schema,
            )
        return [row["tablename"] for row in rows]

    async def _fetch_indexes(self) -> list[str]:
        assert self.store.pool is not None
        async with self.store.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT indexname FROM pg_indexes WHERE schemaname = $1",
                self.test_schema,
            )
        return [row["indexname"] for row in rows]


class TestStoreBasePingClosed(unittest.TestCase):
    """Verify ping returns False when pool is not initialized."""

    def test_ping_without_start(self) -> None:
        store = LogStoreBase(database_url=_database_url())
        loop = asyncio.new_event_loop()
        try:  # noqa: WPS501 - finally-only is correct: loop must close regardless
            self.assertFalse(loop.run_until_complete(store.ping()))
        finally:
            loop.close()


class TestRowHelpers(unittest.TestCase):
    """Validate row normalization helpers."""

    def test_parse_timestamp_none(self) -> None:
        self.assertIsNone(parse_timestamp(None))

    def test_parse_timestamp_empty_string(self) -> None:
        self.assertIsNone(parse_timestamp(""))

    def test_parse_timestamp_isoformat(self) -> None:
        ts = parse_timestamp("2025-01-01T00:00:00+00:00")
        self.assertIsNotNone(ts)
        assert ts is not None
        self.assertEqual(ts.year, 2025)

    def test_normalize_value_passthrough(self) -> None:
        self.assertEqual(normalize_value(42), 42)
        self.assertEqual(normalize_value("hello"), "hello")

    def test_row_to_dict_none(self) -> None:
        self.assertIsNone(row_to_dict(None))

    def test_row_to_dict_basic(self) -> None:
        fake_row: Any = {"name": "test", "count": 5}
        result = row_to_dict(fake_row)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["name"], "test")
        self.assertEqual(result["count"], 5)
