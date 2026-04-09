"""Tests for ingest service orchestration."""

from __future__ import annotations

import unittest

from core.agent_log_analysis.config import AgentLogAnalysisConfig
from core.agent_log_analysis.errors import EventConflictError
from core.agent_log_analysis.ingest_service import IngestService
from core.agent_log_analysis.validation_ingest import IngestValidator


class TestIngestService(unittest.IsolatedAsyncioTestCase):
    """Verify ingest-service orchestration and result mapping."""

    async def test_ingest_event_success(self) -> None:
        store = _FakeStore()
        service = _service(store)
        response = await service.ingest_event(_inference_payload())
        self.assertEqual(response.result.event_id, "evt-1")
        self.assertEqual(response.result.status, "ok")
        self.assertFalse(response.result.duplicate)
        self.assertEqual(len(store.inserted_events), 1)

    async def test_ingest_event_duplicate(self) -> None:
        store = _FakeStore(inserted=False)
        service = _service(store)
        response = await service.ingest_event(_inference_payload())
        self.assertTrue(response.result.duplicate)
        self.assertEqual(response.result.status, "ok")

    async def test_ingest_batch_preserves_order(self) -> None:
        store = _FakeStore()
        service = _service(store)
        response = await service.ingest_batch(
            {
                "events": [
                    _inference_payload(event_id="evt-1"),
                    _inference_payload(event_id=""),
                    _action_payload(event_id="evt-3"),
                ]
            }
        )
        self.assertEqual(len(response.items), 3)
        self.assertEqual(response.items[0].event_id, "evt-1")
        self.assertEqual(response.items[0].status, "ok")
        self.assertEqual(response.items[1].status, "error")
        self.assertEqual(response.items[1].error_code, "VALIDATION_ERROR")
        self.assertEqual(response.items[2].event_id, "evt-3")

    async def test_ingest_batch_conflict_maps_to_error_item(self) -> None:
        store = _FakeStore(conflict_event_id="evt-2")
        service = _service(store)
        response = await service.ingest_batch(
            {"events": [_inference_payload(event_id="evt-1"), _inference_payload(event_id="evt-2")]}
        )
        self.assertEqual(response.items[0].status, "ok")
        self.assertEqual(response.items[1].status, "error")
        self.assertEqual(response.items[1].error_code, "EVENT_ID_CONFLICT")


class _FakeStore:
    def __init__(
        self,
        *,
        inserted: bool = True,
        conflict_event_id: str | None = None,
    ) -> None:
        self._inserted = inserted
        self._conflict_event_id = conflict_event_id
        self.inserted_events: list[dict[str, object]] = []
        self.inserted_raw_logs: list[dict[str, object]] = []

    async def insert_event(self, event_row: dict[str, object], labels: dict[str, str]) -> bool:
        self.inserted_events.append({**event_row, "labels": labels})
        if event_row["event_id"] == self._conflict_event_id:
            raise EventConflictError(str(event_row["event_id"]))
        return self._inserted

    async def insert_raw_log(self, raw_row: dict[str, object]) -> int:
        self.inserted_raw_logs.append(raw_row)
        return len(self.inserted_raw_logs)


def _service(store: _FakeStore) -> IngestService:
    return IngestService(store=store, validator=IngestValidator(_config()))


def _config() -> AgentLogAnalysisConfig:
    return AgentLogAnalysisConfig(
        host="0.0.0.0",
        port=8794,
        database_url="postgresql://example",
        db_schema="agent_log_analysis",
        ingest_token="",
        query_page_default=50,
        query_page_max=200,
        query_window_hours=24,
        event_retention_days=30,
        raw_retention_days=7,
        max_labels_per_event=20,
        max_metadata_bytes=16384,
        max_raw_payload_bytes=65536,
        max_raw_message_bytes=16384,
        max_error_message_bytes=4096,
        max_correlation_nodes=200,
        max_aggregation_group_keys=3,
    )


def _inference_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "event_id": "evt-1",
        "event_type": "inference_event",
        "occurred_at": "2025-01-01T00:00:00Z",
        "agent_slug": "agent-a",
        "labels": {"phase": "run"},
        "metadata": {"seq": 1},
        "raw_payload": {"provider": "openai"},
        "raw_logs": [
            {
                "occurred_at": "2025-01-01T00:00:00Z",
                "level": "INFO",
                "raw_message": "hello",
            }
        ],
        "inference": {
            "model_name": "gpt-4o",
            "provider_name": "openai",
            "request_kind": "chat",
            "status": "success",
            "latency_ms": 12,
        },
    }
    payload.update(overrides)
    return payload


def _action_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "event_id": "evt-2",
        "event_type": "action_event",
        "occurred_at": "2025-01-01T00:00:00Z",
        "agent_slug": "agent-a",
        "action": {
            "action_kind": "tool_call",
            "status": "success",
            "target_name": "send_message",
        },
    }
    payload.update(overrides)
    return payload
