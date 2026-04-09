"""Tests for event point lookup and agent isolation."""

from __future__ import annotations

import asyncio
import unittest
import uuid

from core.agent_log_analysis.store import LogStore
from core.agent_log_analysis.store_query_sql import EventQueryParams
from core.agent_log_analysis.tests.store_query_support import (
    _BASE_TIME,
    _TEST_SCHEMA_PREFIX,
    _WINDOW,
    database_url,
    make_event_row,
)


class TestPointLookup(unittest.TestCase):
    """Verify point lookup by event_id."""

    loop: asyncio.AbstractEventLoop
    store: LogStore

    @classmethod
    def setUpClass(cls) -> None:
        cls.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(cls.loop)
        cls.store = LogStore(
            database_url=database_url(),
            schema_name=_TEST_SCHEMA_PREFIX + uuid.uuid4().hex[:8],
        )
        cls.loop.run_until_complete(cls.store.start())

    @classmethod
    def tearDownClass(cls) -> None:
        cls.loop.run_until_complete(cls.store.close())
        cls.loop.run_until_complete(cls.store.drop_schema())
        cls.loop.close()
        asyncio.set_event_loop(None)

    def test_existing_event(self) -> None:
        event_id = uuid.uuid4().hex
        row = make_event_row(event_id=event_id)
        self.loop.run_until_complete(self.store.insert_event(row, {}))
        found = self.loop.run_until_complete(self.store.get_event_by_id(event_id))
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found["event_id"], event_id)

    def test_missing_event(self) -> None:
        found = self.loop.run_until_complete(
            self.store.get_event_by_id("nonexistent"),
        )
        self.assertIsNone(found)


class TestAgentIsolation(unittest.TestCase):
    """Verify queries only return events for the requested agent."""

    loop: asyncio.AbstractEventLoop
    store: LogStore

    @classmethod
    def setUpClass(cls) -> None:
        cls.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(cls.loop)
        cls.store = LogStore(
            database_url=database_url(),
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

    def test_agent_a_only(self) -> None:
        rows = self.loop.run_until_complete(self.store.query_events(_agent_params("agent-a")))
        self.assertEqual({row["agent_slug"] for row in rows}, {"agent-a"})
        self.assertEqual(len(rows), 3)

    def test_agent_b_only(self) -> None:
        rows = self.loop.run_until_complete(self.store.query_events(_agent_params("agent-b")))
        self.assertEqual({row["agent_slug"] for row in rows}, {"agent-b"})
        self.assertEqual(len(rows), 2)


def _agent_params(agent_slug: str) -> EventQueryParams:
    return EventQueryParams(
        agent_slug=agent_slug,
        since=_BASE_TIME - _WINDOW,
        until=_BASE_TIME + _WINDOW,
    )


async def _seed_isolation_data(store: LogStore) -> None:  # noqa: WPS476
    for idx in range(3):
        row = make_event_row(
            agent_slug="agent-a",
            occurred_at=_BASE_TIME.replace(minute=idx),
        )
        await store.insert_event(row, {})  # noqa: WPS476
    for idx in range(2):
        row = make_event_row(
            agent_slug="agent-b",
            occurred_at=_BASE_TIME.replace(minute=idx),
        )
        await store.insert_event(row, {})  # noqa: WPS476
