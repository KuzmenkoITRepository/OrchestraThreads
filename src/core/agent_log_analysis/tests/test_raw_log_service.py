"""Tests for raw log service behavior."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from core.agent_log_analysis.raw_log_models import RawLogLevel
from core.agent_log_analysis.store_raw_logs import RawLogQueryParams
from core.agent_log_analysis.validation_query_models import ValidatedRawLogQuery

_BASE_TIME = datetime(2025, 1, 1, tzinfo=UTC)


class TestRawLogService(unittest.IsolatedAsyncioTestCase):
    """Verify raw log page shaping and service-side filters."""

    async def test_returns_typed_page(self) -> None:
        from core.agent_log_analysis.raw_log_service import RawLogService

        rows = [_row(3), _row(2)]
        store = _FakeRawLogStore(rows)
        service = RawLogService(store=store)

        page = await service.get_agent_raw_logs(_validated(limit=3))

        self.assertEqual(page.agent_slug, "agent-a")
        self.assertEqual([item.log_id for item in page.items], [3, 2])
        self.assertEqual(page.items[0].raw_message, "message-3")
        self.assertEqual(page.items[0].raw_payload_json, {"idx": 3})
        self.assertIsNone(page.next_cursor)
        self.assertEqual(store.calls[0], _store_params(limit=3))

    async def test_builds_next_cursor_at_limit(self) -> None:
        from core.agent_log_analysis.raw_log_service import RawLogService

        rows = [_row(3), _row(2)]
        service = RawLogService(store=_FakeRawLogStore(rows))

        page = await service.get_agent_raw_logs(_validated(limit=2))

        self.assertEqual(page.next_cursor, "2025-01-01T00:02:00Z|2")

    async def test_applies_service_filters(self) -> None:
        from core.agent_log_analysis.raw_log_service import RawLogService

        rows = [
            _row(3, event_id="evt-keep", level="ERROR", source="stderr"),
            _row(2, event_id="evt-drop", level="INFO", source="stdout"),
            _row(1, event_id="evt-keep", level="ERROR", source="stderr"),
        ]
        service = RawLogService(store=_FakeRawLogStore(rows))

        page = await service.get_agent_raw_logs(
            _validated(
                limit=2,
                event_id="evt-keep",
                level=RawLogLevel.ERROR,
                source="stderr",
            ),
        )

        self.assertEqual([item.log_id for item in page.items], [3, 1])
        self.assertEqual(page.next_cursor, "2025-01-01T00:01:00Z|1")

    async def test_returns_empty_page(self) -> None:
        from core.agent_log_analysis.raw_log_service import RawLogService

        service = RawLogService(store=_FakeRawLogStore([]))

        page = await service.get_agent_raw_logs(_validated(limit=2))

        self.assertEqual(page.agent_slug, "agent-a")
        self.assertEqual(page.items, [])
        self.assertIsNone(page.next_cursor)


class _FakeRawLogStore:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows
        self.calls: list[RawLogQueryParams] = []

    async def query_raw_logs(self, params: RawLogQueryParams) -> list[dict[str, object]]:
        self.calls.append(params)
        rows = [row for row in self._rows if row["agent_slug"] == params.agent_slug]
        if params.cursor_occurred_at is not None and params.cursor_log_id is not None:
            rows = [
                row
                for row in rows
                if (row["occurred_at"], row["log_id"])
                < (
                    params.cursor_occurred_at,
                    params.cursor_log_id,
                )
            ]
        return rows[: params.limit]


def _validated(
    *,
    limit: int,
    event_id: str | None = None,
    level: RawLogLevel | None = None,
    source: str | None = None,
) -> ValidatedRawLogQuery:
    return ValidatedRawLogQuery(
        store_params=_store_params(limit=limit),
        event_id=event_id,
        level=level,
        source=source,
    )


def _store_params(limit: int) -> RawLogQueryParams:
    return RawLogQueryParams(
        agent_slug="agent-a",
        since=_BASE_TIME,
        until=_BASE_TIME + timedelta(hours=1),
        limit=limit,
        run_id="run-1",
        thread_id="thread-1",
        correlation_id="corr-1",
    )


def _row(
    log_id: int,
    *,
    event_id: str | None = None,
    level: str = "INFO",
    source: str = "stdout",
) -> dict[str, object]:
    return {
        "log_id": log_id,
        "event_id": event_id,
        "occurred_at": _BASE_TIME + timedelta(minutes=log_id),
        "received_at": _BASE_TIME + timedelta(minutes=log_id, seconds=1),
        "agent_slug": "agent-a",
        "run_id": "run-1",
        "thread_id": "thread-1",
        "correlation_id": "corr-1",
        "source": source,
        "level": level,
        "raw_message": f"message-{log_id}",
        "raw_payload_json": {"idx": log_id},
    }
