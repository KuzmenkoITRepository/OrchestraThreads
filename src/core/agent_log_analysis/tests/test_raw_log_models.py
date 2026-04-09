"""Tests for raw log record and page DTOs."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from core.agent_log_analysis.raw_log_models import (
    RawLogLevel,
    RawLogPage,
    RawLogRecord,
)


class TestRawLogLevel(unittest.TestCase):
    """Test raw log level enum."""

    def test_level_values(self) -> None:
        levels = [m.value for m in RawLogLevel]
        expected = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        self.assertEqual(levels, expected)


class TestRawLogRecord(unittest.TestCase):
    """Test raw log record DTO."""

    def test_frozen(self) -> None:
        record = _make_record()
        with self.assertRaises(AttributeError):
            record.raw_message = "changed"  # type: ignore[misc]

    def test_optional_payload(self) -> None:
        record = _make_record()
        self.assertIsNone(record.raw_payload_json)


class TestRawLogPage(unittest.TestCase):
    """Test raw log page DTO."""

    def test_empty_page(self) -> None:
        page = RawLogPage(agent_slug="test-agent", items=[])
        self.assertEqual(page.agent_slug, "test-agent")
        self.assertIsNone(page.next_cursor)

    def test_page_with_items(self) -> None:
        record = _make_record()
        page = RawLogPage(agent_slug="test-agent", items=[record])
        self.assertEqual(len(page.items), 1)


def _make_record() -> RawLogRecord:
    now = datetime.now(tz=UTC)
    return RawLogRecord(
        log_id=1,
        event_id=None,
        occurred_at=now,
        received_at=now,
        agent_slug="test-agent",
        run_id=None,
        thread_id=None,
        correlation_id=None,
        source="test",
        level=RawLogLevel.INFO,
        raw_message="hello",
    )
