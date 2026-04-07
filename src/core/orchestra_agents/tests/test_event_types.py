"""Tests for normalized event types."""

from __future__ import annotations

import pytest

from core.orchestra_agents.agent_mux_runtime.event_types import NormalizedEvent


def test_normalized_event_construction() -> None:
    event = NormalizedEvent(
        event_id="evt-123",
        source="test",
        routing_key="key-1",
        kind="message",
        payload={"text": "hello"},
        created_at="2026-04-07T09:00:00Z",
    )

    assert event.event_id == "evt-123"
    assert event.source == "test"
    assert event.routing_key == "key-1"
    assert event.kind == "message"
    assert event.payload == {"text": "hello"}
    assert event.created_at == "2026-04-07T09:00:00Z"
    assert event.interrupt is False
    assert event.priority == 10
    assert event.metadata == {}


def test_normalized_event_with_interrupt() -> None:
    event = NormalizedEvent(
        event_id="evt-456",
        source="test",
        routing_key="key-2",
        kind="urgent",
        payload={},
        created_at="2026-04-07T09:00:00Z",
        interrupt=True,
        priority=1,
    )

    assert event.interrupt is True
    assert event.priority == 1


def test_normalized_event_validation_event_id() -> None:
    with pytest.raises(ValueError, match="event_id is required"):
        NormalizedEvent(
            event_id="",
            source="test",
            routing_key="key",
            kind="message",
            payload={},
            created_at="2026-04-07T09:00:00Z",
        )


def test_normalized_event_validation_source() -> None:
    with pytest.raises(ValueError, match="source is required"):
        NormalizedEvent(
            event_id="evt-1",
            source="",
            routing_key="key",
            kind="message",
            payload={},
            created_at="2026-04-07T09:00:00Z",
        )


def test_normalized_event_validation_routing_key() -> None:
    with pytest.raises(ValueError, match="routing_key is required"):
        NormalizedEvent(
            event_id="evt-1",
            source="test",
            routing_key="",
            kind="message",
            payload={},
            created_at="2026-04-07T09:00:00Z",
        )


def test_normalized_event_no_thread_references() -> None:
    event = NormalizedEvent(
        event_id="evt-789",
        source="test",
        routing_key="key-3",
        kind="message",
        payload={"data": "test"},
        created_at="2026-04-07T09:00:00Z",
    )

    event_dict = event.__dict__
    assert "thread_id" not in event_dict
    assert "thread" not in str(event_dict).lower()
