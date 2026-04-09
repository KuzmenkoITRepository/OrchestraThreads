"""Tests for ingest and get-event API models."""

from __future__ import annotations

import unittest

from core.agent_log_analysis.api_models import (
    GetEventResult,
    IngestBatchRequest,
    IngestEventRequest,
    IngestEventResult,
)


class TestIngestRequest(unittest.TestCase):
    """Test ingest request DTO."""

    def test_frozen(self) -> None:
        req = _make_ingest_request()
        with self.assertRaises(AttributeError):
            req.event_id = "changed"  # type: ignore[misc]

    def test_default_raw_logs_empty(self) -> None:
        req = _make_ingest_request()
        self.assertEqual(req.raw_logs, [])

    def test_default_labels_empty(self) -> None:
        req = _make_ingest_request()
        self.assertEqual(req.labels, {})


class TestIngestBatchAndResult(unittest.TestCase):
    """Test batch request and result DTOs."""

    def test_batch_request(self) -> None:
        batch = IngestBatchRequest(events=[_make_ingest_request()])
        self.assertEqual(len(batch.events), 1)

    def test_result_duplicate_default(self) -> None:
        result = IngestEventResult(event_id="e1", status="ok")
        self.assertFalse(result.duplicate)

    def test_result_frozen(self) -> None:
        result = IngestEventResult(event_id="e1", status="ok")
        with self.assertRaises(AttributeError):
            result.event_id = "changed"  # type: ignore[misc]


class TestGetEventResult(unittest.TestCase):
    """Test event lookup result DTO."""

    def test_frozen(self) -> None:
        result = _make_get_event_result()
        with self.assertRaises(AttributeError):
            result.event_id = "changed"  # type: ignore[misc]

    def test_default_labels(self) -> None:
        result = _make_get_event_result()
        self.assertEqual(result.labels, {})

    def test_default_raw_payload_attached(self) -> None:
        result = _make_get_event_result()
        self.assertFalse(result.raw_payload_attached)


def _make_ingest_request() -> IngestEventRequest:
    return IngestEventRequest(
        event_id="evt-1",
        event_type="inference_event",
        occurred_at="2025-01-01T00:00:00Z",
        agent_slug="test-agent",
    )


def _make_get_event_result() -> GetEventResult:
    return GetEventResult(
        event_id="evt-1",
        event_type="inference_event",
        occurred_at="2025-01-01T00:00:00Z",
        received_at="2025-01-01T00:00:01Z",
        agent_slug="test-agent",
    )
