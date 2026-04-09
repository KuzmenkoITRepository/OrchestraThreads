"""Tests for timeline service behavior."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from core.agent_log_analysis.store_query_sql import EventQueryParams
from core.agent_log_analysis.timeline_service import TimelineService
from core.agent_log_analysis.validation_time import serialize_timestamp

_BASE_TIME = datetime(2025, 1, 1, tzinfo=UTC)
_WINDOW = timedelta(hours=1)


class TestTimelineService(unittest.IsolatedAsyncioTestCase):
    """Verify deterministic timeline page mapping."""

    async def test_get_agent_timeline_returns_desc_items(self) -> None:
        rows = [_stored_row("evt-2", event_type="action_event", minute=1), _stored_row("evt-1")]
        service = TimelineService(store=_FakeTimelineStore(rows))
        page = await service.get_agent_timeline(_params(limit=3))
        self.assertEqual([item.event_id for item in page.items], ["evt-2", "evt-1"])
        self.assertEqual(
            [item.event_type for item in page.items], ["action_event", "inference_event"]
        )
        self.assertIsNone(page.next_cursor)

    async def test_get_agent_timeline_sets_next_cursor(self) -> None:
        rows = [_stored_row("evt-2", minute=1), _stored_row("evt-1")]
        service = TimelineService(store=_FakeTimelineStore(rows))
        page = await service.get_agent_timeline(_params(limit=2))
        self.assertEqual(page.next_cursor, f"{serialize_timestamp(_BASE_TIME)}|evt-1")

    async def test_get_agent_timeline_returns_empty_page(self) -> None:
        service = TimelineService(store=_FakeTimelineStore([]))
        page = await service.get_agent_timeline(_params(limit=2))
        self.assertEqual(page.agent_slug, "agent-a")
        self.assertEqual(page.items, [])
        self.assertIsNone(page.next_cursor)


class _FakeTimelineStore:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    async def query_events(self, params: EventQueryParams) -> list[dict[str, object]]:
        if params.agent_slug == "agent-a":
            return list(self._rows)
        return []


def _params(limit: int) -> EventQueryParams:
    return EventQueryParams(
        agent_slug="agent-a",
        since=_BASE_TIME - _WINDOW,
        until=_BASE_TIME + _WINDOW,
        limit=limit,
    )


def _stored_row(
    event_id: str,
    *,
    event_type: str = "inference_event",
    minute: int = 0,
) -> dict[str, object]:
    return {
        "event_id": event_id,
        "event_type": event_type,
        "occurred_at": _BASE_TIME.replace(minute=minute).isoformat(),
        "received_at": (_BASE_TIME.replace(minute=minute) + timedelta(seconds=1)).isoformat(),
        "agent_slug": "agent-a",
        "run_id": None,
        "thread_id": None,
        "correlation_id": None,
        "parent_event_id": None,
        "status": "success",
        "metadata_json": {"seq": minute},
        "payload_json": {"labels": {}, "event_type": event_type},
        "raw_payload_attached": False,
    }
