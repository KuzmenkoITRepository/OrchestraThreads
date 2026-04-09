"""Tests for event query service behavior."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from core.agent_log_analysis.errors import EventNotFoundError
from core.agent_log_analysis.event_query_service import EventQueryService
from core.agent_log_analysis.store_query_sql import EventQueryParams
from core.agent_log_analysis.validation_time import serialize_timestamp

_BASE_TIME = datetime(2025, 1, 1, tzinfo=UTC)
_WINDOW = timedelta(hours=1)


class TestEventQueryService(unittest.IsolatedAsyncioTestCase):
    """Verify exact lookup and paginated event-query mapping."""

    async def test_get_event_returns_lookup_dto(self) -> None:
        service = EventQueryService(store=_FakeQueryStore(event_row=_stored_row("evt-1")))
        response = await service.get_event("evt-1")
        self.assertEqual(response.event.event_id, "evt-1")
        self.assertEqual(response.event.labels, {"phase": "run"})
        self.assertTrue(response.event.raw_payload_attached)

    async def test_get_event_not_found(self) -> None:
        service = EventQueryService(store=_FakeQueryStore())
        with self.assertRaises(EventNotFoundError):
            await service.get_event("missing")

    async def test_query_agent_events_returns_typed_page(self) -> None:
        rows = [_stored_row("evt-1"), _stored_row("evt-2", minute=1)]
        service = EventQueryService(store=_FakeQueryStore(query_rows=rows))
        page = await service.query_agent_events(_params(limit=3))
        self.assertEqual(page.agent_slug, "agent-a")
        self.assertEqual(page.window_start, serialize_timestamp(_BASE_TIME - _WINDOW))
        self.assertEqual(page.window_end, serialize_timestamp(_BASE_TIME + _WINDOW))
        self.assertEqual([item.event_id for item in page.items], ["evt-1", "evt-2"])
        self.assertIsNone(page.next_cursor)

    async def test_query_agent_events_sets_next_cursor(self) -> None:
        rows = [_stored_row("evt-1"), _stored_row("evt-2", minute=1)]
        service = EventQueryService(store=_FakeQueryStore(query_rows=rows))
        page = await service.query_agent_events(_params(limit=2))
        self.assertEqual(
            page.next_cursor,
            f"{serialize_timestamp(_BASE_TIME.replace(minute=1))}|evt-2",
        )


class _FakeQueryStore:
    def __init__(
        self,
        *,
        event_row: dict[str, object] | None = None,
        query_rows: list[dict[str, object]] | None = None,
    ) -> None:
        self._event_row = event_row
        self._query_rows = query_rows or []

    async def get_event_by_id(self, event_id: str) -> dict[str, object] | None:
        if self._event_row is None or self._event_row["event_id"] != event_id:
            return None
        return self._event_row

    async def query_events(self, params: EventQueryParams) -> list[dict[str, object]]:
        if params.agent_slug == "agent-a":
            return list(self._query_rows)
        return []


def _params(limit: int) -> EventQueryParams:
    return EventQueryParams(
        agent_slug="agent-a",
        since=_BASE_TIME - _WINDOW,
        until=_BASE_TIME + _WINDOW,
        limit=limit,
    )


def _stored_row(event_id: str, *, minute: int = 0) -> dict[str, object]:
    return {
        "event_id": event_id,
        "event_type": "inference_event",
        "occurred_at": _BASE_TIME.replace(minute=minute).isoformat(),
        "received_at": (_BASE_TIME.replace(minute=minute) + timedelta(seconds=1)).isoformat(),
        "agent_slug": "agent-a",
        "run_id": None,
        "thread_id": None,
        "correlation_id": None,
        "parent_event_id": None,
        "status": "success",
        "metadata_json": {"seq": minute},
        "payload_json": {
            "labels": {"phase": "run"},
            "inference": {"model_name": "gpt-4o"},
            "raw_payload": {"provider": "openai"},
        },
        "raw_payload_attached": True,
    }
