"""Tests for label filters and cursor pagination in event queries."""

from __future__ import annotations

import asyncio
import unittest
import uuid
from datetime import datetime

from core.agent_log_analysis.store import LogStore
from core.agent_log_analysis.store_query_sql import EventQueryParams
from core.agent_log_analysis.tests.store_query_support import (
    _BASE_TIME,
    _TEST_SCHEMA_PREFIX,
    _WINDOW,
    database_url,
    make_event_row,
)


class TestLabelFilters(unittest.TestCase):
    """Verify ANDed label-filter behavior."""

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
        cls.loop.run_until_complete(_seed_label_data(cls.store))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.loop.run_until_complete(cls.store.close())
        cls.loop.run_until_complete(cls.store.drop_schema())
        cls.loop.close()
        asyncio.set_event_loop(None)

    def test_single_label_filter(self) -> None:
        rows = self.loop.run_until_complete(
            self.store.query_events(
                EventQueryParams(
                    agent_slug="label-agent",
                    since=_BASE_TIME - _WINDOW,
                    until=_BASE_TIME + _WINDOW,
                    label_filters={"env": "prod"},
                ),
            ),
        )
        self.assertEqual(len(rows), 2)

    def test_and_label_filter(self) -> None:
        rows = self.loop.run_until_complete(
            self.store.query_events(
                EventQueryParams(
                    agent_slug="label-agent",
                    since=_BASE_TIME - _WINDOW,
                    until=_BASE_TIME + _WINDOW,
                    label_filters={"env": "prod", "team": "infra"},
                ),
            ),
        )
        self.assertEqual(len(rows), 1)


class TestPagination(unittest.TestCase):
    """Verify deterministic cursor pagination."""

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
        cls.loop.run_until_complete(_seed_pagination_data(cls.store))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.loop.run_until_complete(cls.store.close())
        cls.loop.run_until_complete(cls.store.drop_schema())
        cls.loop.close()
        asyncio.set_event_loop(None)

    def test_limit_respected(self) -> None:
        rows = self.loop.run_until_complete(self.store.query_events(_page_params(limit=2)))
        self.assertEqual(len(rows), 2)

    def test_cursor_advances(self) -> None:
        first_page = self.loop.run_until_complete(self.store.query_events(_page_params(limit=2)))
        self.assertEqual(len(first_page), 2)
        second_page = self.loop.run_until_complete(
            self.store.query_events(_cursor_params(first_page[-1])),
        )
        self.assertEqual(len(second_page), 2)
        self.assertEqual(
            {row["event_id"] for row in first_page} & {row["event_id"] for row in second_page},
            set(),
        )


def _page_params(limit: int) -> EventQueryParams:
    return EventQueryParams(
        agent_slug="page-agent",
        since=_BASE_TIME - _WINDOW,
        until=_BASE_TIME + _WINDOW,
        limit=limit,
    )


def _cursor_params(last_row: dict[str, str]) -> EventQueryParams:
    return EventQueryParams(
        agent_slug="page-agent",
        since=_BASE_TIME - _WINDOW,
        until=_BASE_TIME + _WINDOW,
        limit=2,
        cursor_occurred_at=datetime.fromisoformat(last_row["occurred_at"]),
        cursor_event_id=last_row["event_id"],
    )


async def _seed_label_data(store: LogStore) -> None:  # noqa: WPS476
    row = make_event_row(agent_slug="label-agent")
    await store.insert_event(row, {"env": "prod", "team": "infra"})
    row = make_event_row(agent_slug="label-agent")
    await store.insert_event(row, {"env": "prod", "team": "backend"})
    row = make_event_row(agent_slug="label-agent")
    await store.insert_event(row, {"env": "dev"})  # noqa: WPS476


async def _seed_pagination_data(store: LogStore) -> None:  # noqa: WPS476
    for minute in range(5):
        row = make_event_row(
            agent_slug="page-agent",
            occurred_at=_BASE_TIME.replace(minute=minute),
        )
        await store.insert_event(row, {})  # noqa: WPS476
