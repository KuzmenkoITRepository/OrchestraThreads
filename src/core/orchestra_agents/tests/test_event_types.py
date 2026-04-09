"""Tests for normalized event types."""

from __future__ import annotations

import pytest

from core.orchestra_agents.backends.agent_mux.internal.event_types import NormalizedEvent

_TEST_SOURCE = "test"
_MESSAGE_KIND = "message"
_CREATED_AT = "2026-04-07T09:00:00Z"


def test_normalized_event_required_fields() -> None:
    event = NormalizedEvent(
        event_id="evt-123",
        source=_TEST_SOURCE,
        routing_key="key-1",
        kind=_MESSAGE_KIND,
        payload={"text": "hello"},
        created_at=_CREATED_AT,
    )

    assert event.event_id == "evt-123"
    assert event.source == _TEST_SOURCE
    assert event.routing_key == "key-1"
    assert event.kind == _MESSAGE_KIND
    assert event.payload == {"text": "hello"}


def test_normalized_event_defaults() -> None:
    event = NormalizedEvent(
        event_id="evt-123",
        source=_TEST_SOURCE,
        routing_key="key-1",
        kind=_MESSAGE_KIND,
        payload={"text": "hello"},
        created_at=_CREATED_AT,
    )

    assert event.created_at == _CREATED_AT
    assert event.interrupt is False
    assert event.priority == 10
    assert event.metadata == {}


def test_normalized_event_with_interrupt() -> None:
    event = NormalizedEvent(
        event_id="evt-456",
        source=_TEST_SOURCE,
        routing_key="key-2",
        kind="urgent",
        payload={},
        created_at=_CREATED_AT,
        interrupt=True,
        priority=1,
    )

    assert event.interrupt is True
    assert event.priority == 1


def test_normalized_event_validation_event_id() -> None:
    with pytest.raises(ValueError, match="event_id is required"):
        NormalizedEvent(
            event_id="",
            source=_TEST_SOURCE,
            routing_key="key",
            kind=_MESSAGE_KIND,
            payload={},
            created_at=_CREATED_AT,
        )


def test_normalized_event_validation_source() -> None:
    with pytest.raises(ValueError, match="source is required"):
        NormalizedEvent(
            event_id="evt-1",
            source="",
            routing_key="key",
            kind=_MESSAGE_KIND,
            payload={},
            created_at=_CREATED_AT,
        )


def test_normalized_event_validation_routing_key() -> None:
    with pytest.raises(ValueError, match="routing_key is required"):
        NormalizedEvent(
            event_id="evt-1",
            source=_TEST_SOURCE,
            routing_key="",
            kind=_MESSAGE_KIND,
            payload={},
            created_at=_CREATED_AT,
        )


def test_normalized_event_no_thread_references() -> None:
    event = NormalizedEvent(
        event_id="evt-789",
        source=_TEST_SOURCE,
        routing_key="key-3",
        kind=_MESSAGE_KIND,
        payload={"data": _TEST_SOURCE},
        created_at=_CREATED_AT,
    )

    event_dict = event.__dict__
    assert "thread_id" not in event_dict
    assert "thread" not in str(event_dict).lower()
