"""Tests for normalized event ingest store."""

from __future__ import annotations

import asyncio
import os
import unittest
import uuid
from datetime import UTC, datetime
from typing import Any

from core.agent_log_analysis.errors import EventConflictError
from core.agent_log_analysis.store import LogStore
from core.agent_log_analysis.store_ingest import EventWithLabels

_TEST_SCHEMA_PREFIX = "ala_ingest_"


def _database_url() -> str:
    return os.getenv(
        "AGENT_LOG_ANALYSIS_TEST_DATABASE_URL",
        os.getenv(
            "ORCHESTRA_THREADS_TEST_DATABASE_URL",
            "postgresql://orchestra:orchestra@127.0.0.1:5432/orchestra_threads",
        ),
    )


def _make_event_row(
    event_id: str | None = None,
    agent_slug: str = "test-agent",
) -> dict[str, Any]:
    return {
        "event_id": event_id or uuid.uuid4().hex,
        "event_type": "inference_event",
        "occurred_at": datetime(2025, 1, 1, tzinfo=UTC),
        "received_at": datetime(2025, 1, 1, 0, 0, 1, tzinfo=UTC),
        "agent_slug": agent_slug,
        "run_id": "run-1",
        "thread_id": None,
        "correlation_id": "corr-1",
        "parent_event_id": None,
        "status": "success",
        "model_name": "gpt-4",
        "provider_name": "openai",
        "request_kind": "chat",
        "action_kind": None,
        "target_name": None,
        "target_agent_slug": None,
        "latency_ms": 120,
        "metadata_json": {"env": "test"},
        "payload_json": {"model": "gpt-4", "tokens": 100},
        "raw_payload_attached": False,
    }


class TestIngestInsert(unittest.TestCase):
    """Verify first-insert and duplicate behavior."""

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

    def test_first_insert_returns_true(self) -> None:
        row = _make_event_row()
        inserted = self.loop.run_until_complete(self.store.insert_event(row, {}))
        self.assertTrue(inserted)

    def test_duplicate_replay_returns_false(self) -> None:
        eid = uuid.uuid4().hex
        row = _make_event_row(event_id=eid)
        self.loop.run_until_complete(self.store.insert_event(row, {}))
        dup = self.loop.run_until_complete(self.store.insert_event(row, {}))
        self.assertFalse(dup)

    def test_conflict_raises(self) -> None:
        eid = uuid.uuid4().hex
        row1 = _make_event_row(event_id=eid)
        self.loop.run_until_complete(self.store.insert_event(row1, {}))
        row2 = _make_event_row(event_id=eid)
        row2["payload_json"] = {"different": True}
        with self.assertRaises(EventConflictError):
            self.loop.run_until_complete(self.store.insert_event(row2, {}))


class TestIngestLabels(unittest.TestCase):
    """Verify label persistence."""

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

    def test_labels_persisted(self) -> None:
        eid = uuid.uuid4().hex
        row = _make_event_row(event_id=eid)
        labels = {"env": "prod", "team": "infra"}
        self.loop.run_until_complete(self.store.insert_event(row, labels))
        fetched = self.loop.run_until_complete(self._fetch_labels(eid))
        self.assertEqual(fetched, labels)

    async def _fetch_labels(self, event_id: str) -> dict[str, str]:
        assert self.store.pool is not None
        async with self.store.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT label_key, label_value FROM agent_log_event_labels WHERE event_id = $1",
                event_id,
            )
        return {r["label_key"]: r["label_value"] for r in rows}


class TestBatchIngest(unittest.TestCase):
    """Verify batch insert with partial success."""

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

    def test_batch_insert(self) -> None:
        rows: list[EventWithLabels] = [(_make_event_row(), {}) for _ in range(3)]
        results = self.loop.run_until_complete(self.store.insert_event_batch(rows))
        self.assertEqual(len(results), 3)
        for inserted, err in results:
            self.assertTrue(inserted)
            self.assertIsNone(err)

    def test_batch_with_conflict(self) -> None:
        eid = uuid.uuid4().hex
        row1 = _make_event_row(event_id=eid)
        self.loop.run_until_complete(self.store.insert_event(row1, {}))
        batch = _build_conflict_batch(eid)
        results = self.loop.run_until_complete(self.store.insert_event_batch(batch))
        self.assertFalse(results[0][0])
        self.assertIsInstance(results[0][1], EventConflictError)
        self.assertTrue(results[1][0])
        self.assertIsNone(results[1][1])


def _build_conflict_batch(eid: str) -> list[EventWithLabels]:
    conflicting = _make_event_row(event_id=eid)
    conflicting["payload_json"] = {"conflict": True}
    ok_row = _make_event_row()
    return [(conflicting, {}), (ok_row, {})]
