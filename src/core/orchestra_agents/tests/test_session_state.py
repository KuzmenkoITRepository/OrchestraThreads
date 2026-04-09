"""Tests for runtime session state."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from core.orchestra_agents.backends.agent_mux.internal.event_types import NormalizedEvent
from core.orchestra_agents.backends.agent_mux.internal.session_state import (
    RuntimeSession,
    load_session_state,
    save_session_state,
)
from core.orchestra_agents.backends.agent_mux.internal.session_types import (
    RoutingKey,
    SessionId,
    SessionLifecycle,
)

_FIXED_TIMESTAMP = "2026-04-07T09:00:00Z"
_SOURCE_TEST = "test"
_KIND_MESSAGE = "message"
_EVT_ID_ONE = "evt-1"


def test_runtime_session_identity_and_defaults() -> None:
    session = RuntimeSession(
        session_id=SessionId("session-1"),
        routing_key=RoutingKey("key-1"),
        lifecycle=SessionLifecycle.IDLE,
    )

    assert (
        session.session_id,
        session.routing_key,
        session.lifecycle,
        session.mailbox,
        session.cli_session_metadata,
        session.timeline,
        session.processed_event_ids,
    ) == (
        "session-1",
        "key-1",
        SessionLifecycle.IDLE,
        [],
        {},
        [],
        set(),
    )


def test_session_append_event() -> None:
    session = RuntimeSession(
        session_id=SessionId("session-2"),
        routing_key=RoutingKey("key-2"),
        lifecycle=SessionLifecycle.IDLE,
    )

    event = NormalizedEvent(
        event_id=_EVT_ID_ONE,
        source=_SOURCE_TEST,
        routing_key="key-2",
        kind=_KIND_MESSAGE,
        payload={},
        created_at=_FIXED_TIMESTAMP,
    )

    session.append_event(event)
    assert len(session.mailbox) == 1
    assert session.mailbox[0].event_id == _EVT_ID_ONE


def test_session_idempotent_append() -> None:
    session = RuntimeSession(
        session_id=SessionId("session-3"),
        routing_key=RoutingKey("key-3"),
        lifecycle=SessionLifecycle.IDLE,
    )

    event = NormalizedEvent(
        event_id="evt-dup",
        source=_SOURCE_TEST,
        routing_key="key-3",
        kind=_KIND_MESSAGE,
        payload={},
        created_at=_FIXED_TIMESTAMP,
    )

    session.append_event(event)
    session.mark_event_processed("evt-dup")
    session.append_event(event)

    assert len(session.mailbox) == 1


def test_session_claim_next_event() -> None:
    session = RuntimeSession(
        session_id=SessionId("session-4"),
        routing_key=RoutingKey("key-4"),
        lifecycle=SessionLifecycle.IDLE,
    )

    event1 = NormalizedEvent(
        event_id=_EVT_ID_ONE,
        source=_SOURCE_TEST,
        routing_key="key-4",
        kind=_KIND_MESSAGE,
        payload={},
        created_at=_FIXED_TIMESTAMP,
    )
    event2 = NormalizedEvent(
        event_id="evt-2",
        source=_SOURCE_TEST,
        routing_key="key-4",
        kind=_KIND_MESSAGE,
        payload={},
        created_at="2026-04-07T09:01:00Z",
    )

    session.append_event(event1)
    session.append_event(event2)

    claimed = session.claim_next_event()
    assert claimed is not None
    assert claimed.event_id == _EVT_ID_ONE
    assert len(session.mailbox) == 1


def test_session_timeline() -> None:
    session = RuntimeSession(
        session_id=SessionId("session-5"),
        routing_key=RoutingKey("key-5"),
        lifecycle=SessionLifecycle.IDLE,
    )

    session.add_timeline_entry("test_event", {"detail": "value"})

    assert len(session.timeline) == 1
    assert session.timeline[0]["event_type"] == "test_event"
    assert session.timeline[0]["metadata"]["detail"] == "value"


def test_session_persistence() -> None:
    with TemporaryDirectory() as tmpdir:
        state_root = Path(tmpdir)

        session = RuntimeSession(
            session_id=SessionId("session-persist"),
            routing_key=RoutingKey("key-persist"),
            lifecycle=SessionLifecycle.IDLE,
            created_at=_FIXED_TIMESTAMP,
        )

        event = NormalizedEvent(
            event_id="evt-persist",
            source=_SOURCE_TEST,
            routing_key="key-persist",
            kind=_KIND_MESSAGE,
            payload={"data": _SOURCE_TEST},
            created_at=_FIXED_TIMESTAMP,
        )
        session.append_event(event)

        save_session_state(session, state_root)

        loaded = load_session_state(SessionId("session-persist"), state_root)
        assert loaded is not None
        assert loaded.session_id == "session-persist"
        assert loaded.routing_key == "key-persist"
        assert len(loaded.mailbox) == 1
        assert loaded.mailbox[0].event_id == "evt-persist"


def test_no_thread_references_in_session() -> None:
    session = RuntimeSession(
        session_id=SessionId("session-6"),
        routing_key=RoutingKey("key-6"),
        lifecycle=SessionLifecycle.IDLE,
    )

    session_dict = session.to_dict()
    assert "thread_id" not in session_dict
    assert "thread" not in str(session_dict).lower()
