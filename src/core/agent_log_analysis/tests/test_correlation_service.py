"""Tests for correlation service behavior."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from core.agent_log_analysis.store_correlation import CorrelationQueryParams

_BASE_TIME = datetime(2025, 1, 1, tzinfo=UTC)


class TestCorrelationService(unittest.IsolatedAsyncioTestCase):
    """Verify correlation chain mapping and truncation."""

    async def test_returns_typed_chain(self) -> None:
        from core.agent_log_analysis.correlation_service import CorrelationService

        rows = [_stored_row("evt-1"), _stored_row("evt-2", minute=1)]
        store = _FakeCorrelationStore(rows)
        service = CorrelationService(store=store)

        chain = await service.get_agent_correlation_chain(_params(max_nodes=3))

        self.assertEqual(chain.agent_slug, "agent-a")
        self.assertEqual(chain.correlation_id, "corr-1")
        self.assertEqual([item.event_id for item in chain.items], ["evt-1", "evt-2"])
        self.assertFalse(chain.truncated)
        self.assertEqual(store.calls, [_params(max_nodes=3)])

    async def test_returns_empty_chain(self) -> None:
        from core.agent_log_analysis.correlation_service import CorrelationService

        service = CorrelationService(store=_FakeCorrelationStore([]))

        chain = await service.get_agent_correlation_chain(_params(max_nodes=3))

        self.assertEqual(chain.items, [])
        self.assertFalse(chain.truncated)

    async def test_marks_truncated_at_cap(self) -> None:
        from core.agent_log_analysis.correlation_service import CorrelationService

        rows = [_stored_row("evt-1"), _stored_row("evt-2", minute=1)]
        service = CorrelationService(store=_FakeCorrelationStore(rows))

        chain = await service.get_agent_correlation_chain(_params(max_nodes=2))

        self.assertTrue(chain.truncated)


class _FakeCorrelationStore:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows
        self.calls: list[CorrelationQueryParams] = []

    async def query_correlation_chain(
        self,
        params: CorrelationQueryParams,
    ) -> list[dict[str, object]]:
        self.calls.append(params)
        return list(self._rows)


def _params(max_nodes: int) -> CorrelationQueryParams:
    return CorrelationQueryParams(
        agent_slug="agent-a",
        correlation_id="corr-1",
        max_nodes=max_nodes,
        run_id="run-1",
        thread_id="thread-1",
    )


def _stored_row(event_id: str, *, minute: int = 0) -> dict[str, object]:
    return {
        "event_id": event_id,
        "event_type": "inference_event",
        "occurred_at": (_BASE_TIME + timedelta(minutes=minute)).isoformat(),
        "received_at": (_BASE_TIME + timedelta(minutes=minute, seconds=1)).isoformat(),
        "agent_slug": "agent-a",
        "run_id": "run-1",
        "thread_id": "thread-1",
        "correlation_id": "corr-1",
        "parent_event_id": None,
        "status": "success",
        "metadata_json": {"seq": minute},
        "payload_json": {
            "labels": {"phase": "run"},
            "inference": {"model_name": "gpt-4o"},
        },
        "raw_payload_attached": False,
    }
