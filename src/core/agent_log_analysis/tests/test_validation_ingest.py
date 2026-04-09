"""Tests for ingest validation rules and normalization."""

from __future__ import annotations

import unittest

from core.agent_log_analysis.config import AgentLogAnalysisConfig
from core.agent_log_analysis.errors import ValidationError
from core.agent_log_analysis.validation_ingest import IngestValidator


class TestValidateIngestEvent(unittest.TestCase):
    """Single-event ingest validation."""

    def setUp(self) -> None:
        self.validator = IngestValidator(_config())

    def test_inference_event_normalizes_payload(self) -> None:
        result = self.validator.validate_event(_inference_payload())
        self.assertEqual(result.request.event_type, "inference_event")
        self.assertEqual(result.request.occurred_at, "2025-01-01T00:00:00Z")
        self.assertEqual(result.request.agent_slug, "agent-a")
        self.assertEqual(
            result.request.inference,
            {
                "model_name": "gpt-4o",
                "provider_name": "openai",
                "request_kind": "chat",
                "status": "success",
                "latency_ms": 12,
            },
        )

    def test_received_at_is_ignored(self) -> None:
        payload = _inference_payload(received_at="2025-01-01T00:00:09Z")
        result = self.validator.validate_event(payload)
        self.assertFalse(hasattr(result.request, "received_at"))

    def test_required_fields_enforced(self) -> None:
        with self.assertRaises(ValidationError):
            self.validator.validate_event(_inference_payload(event_id=""))

    def test_raw_logs_inherit_parent_scope(self) -> None:
        payload = _inference_payload(
            raw_logs=[
                {
                    "occurred_at": "2025-01-01T00:00:00Z",
                    "level": "INFO",
                    "raw_message": "hello",
                }
            ]
        )
        result = self.validator.validate_event(payload)
        self.assertEqual(result.request.raw_logs[0]["event_id"], "evt-1")
        self.assertEqual(result.request.raw_logs[0]["agent_slug"], "agent-a")
        self.assertEqual(result.request.raw_logs[0]["level"], "INFO")


class TestValidateIngestBounds(unittest.TestCase):
    """Bound checks for ingest requests."""

    def setUp(self) -> None:
        self.validator = IngestValidator(_config())

    def test_label_count_cap_enforced(self) -> None:
        labels = {f"k{index}": "v" for index in range(21)}
        with self.assertRaises(ValidationError):
            self.validator.validate_event(_inference_payload(labels=labels))

    def test_empty_label_key_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            self.validator.validate_event(_inference_payload(labels={"": "v"}))

    def test_metadata_size_cap_enforced(self) -> None:
        payload = _inference_payload(metadata={"blob": "x" * 300})
        validator = IngestValidator(_config(max_metadata_bytes=32))
        with self.assertRaises(ValidationError):
            validator.validate_event(payload)

    def test_error_message_size_cap_enforced(self) -> None:
        payload = _action_payload(
            action={
                "action_kind": "tool_call",
                "status": "error",
                "error_message": "x" * 30,
            }
        )
        validator = IngestValidator(_config(max_error_message_bytes=8))
        with self.assertRaises(ValidationError):
            validator.validate_event(payload)


class TestValidateIngestBatch(unittest.TestCase):
    """Batch ingest validation behavior."""

    def setUp(self) -> None:
        self.validator = IngestValidator(_config())

    def test_batch_keeps_valids_and_errors(self) -> None:
        payload = {
            "events": [
                _inference_payload(event_id="evt-1"),
                _inference_payload(event_id=""),
                _action_payload(event_id="evt-3"),
            ]
        }
        result = self.validator.validate_batch(payload)
        self.assertEqual([item.request.event_id for item in result.events], ["evt-1", "evt-3"])
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(result.errors[0].index, 1)
        self.assertEqual(result.errors[0].error_code, "VALIDATION_ERROR")


def _config(
    *,
    max_metadata_bytes: int = 16384,
    max_error_message_bytes: int = 4096,
) -> AgentLogAnalysisConfig:
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
        max_metadata_bytes=max_metadata_bytes,
        max_raw_payload_bytes=65536,
        max_raw_message_bytes=16384,
        max_error_message_bytes=max_error_message_bytes,
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
