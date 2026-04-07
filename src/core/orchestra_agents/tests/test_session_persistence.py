"""Tests for session state persistence."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from core.orchestra_agents.agent_mux_runtime.event_types import NormalizedEvent
from core.orchestra_agents.agent_mux_runtime.session_state import (
    RuntimeSession,
    load_session_state,
    save_session_state,
)
from core.orchestra_agents.agent_mux_runtime.session_types import (
    RoutingKey,
    SessionId,
    SessionLifecycle,
)


def test_session_save_and_reload() -> None:
    with TemporaryDirectory() as tmpdir:
        state_root = Path(tmpdir)

        session = RuntimeSession(
            session_id=SessionId("session-save-reload"),
            routing_key=RoutingKey("key-save-reload"),
            lifecycle=SessionLifecycle.IDLE,
            created_at="2026-04-07T09:00:00Z",
        )

        event = NormalizedEvent(
            event_id="evt-save",
            source="test",
            routing_key="key-save-reload",
            kind="message",
            payload={"data": "test"},
            created_at="2026-04-07T09:00:00Z",
        )
        session.append_event(event)
        session.add_timeline_entry("test_action", {"detail": "value"})

        save_session_state(session, state_root)

        loaded = load_session_state(SessionId("session-save-reload"), state_root)

        assert loaded is not None
        assert loaded.session_id == session.session_id
        assert loaded.routing_key == session.routing_key
        assert loaded.lifecycle == session.lifecycle
        assert len(loaded.mailbox) == 1
        assert loaded.mailbox[0].event_id == "evt-save"
        assert len(loaded.timeline) == 1
        assert loaded.timeline[0]["event_type"] == "test_action"


def test_session_reset_clears_state() -> None:
    with TemporaryDirectory() as tmpdir:
        state_root = Path(tmpdir)

        session = RuntimeSession(
            session_id=SessionId("session-reset"),
            routing_key=RoutingKey("key-reset"),
            lifecycle=SessionLifecycle.BUSY,
            created_at="2026-04-07T09:00:00Z",
        )

        event = NormalizedEvent(
            event_id="evt-reset",
            source="test",
            routing_key="key-reset",
            kind="message",
            payload={},
            created_at="2026-04-07T09:00:00Z",
        )
        session.append_event(event)
        session.mark_event_processed("evt-reset")

        save_session_state(session, state_root)

        session_reset = RuntimeSession(
            session_id=SessionId("session-reset"),
            routing_key=RoutingKey("key-reset"),
            lifecycle=SessionLifecycle.IDLE,
            created_at="2026-04-07T09:00:00Z",
        )

        save_session_state(session_reset, state_root)

        loaded = load_session_state(SessionId("session-reset"), state_root)
        assert loaded is not None
        assert loaded.lifecycle == SessionLifecycle.IDLE
        assert len(loaded.mailbox) == 0
        assert len(loaded.processed_event_ids) == 0


def test_one_canonical_session_state_file() -> None:
    with TemporaryDirectory() as tmpdir:
        state_root = Path(tmpdir)

        session = RuntimeSession(
            session_id=SessionId("session-canonical"),
            routing_key=RoutingKey("key-canonical"),
            lifecycle=SessionLifecycle.IDLE,
            created_at="2026-04-07T09:00:00Z",
        )

        save_session_state(session, state_root)

        session_dir = state_root / "sessions" / "session-canonical"
        assert session_dir.exists()

        state_file = session_dir / "session_state.json"
        assert state_file.exists()

        other_files = [
            f
            for f in session_dir.iterdir()
            if f.name != "session_state.json" and f.name != "artifacts"
        ]
        assert len(other_files) == 0


def test_artifact_directory_stable() -> None:
    with TemporaryDirectory() as tmpdir:
        state_root = Path(tmpdir)

        artifact_dir = state_root / "sessions" / "session-artifact" / "artifacts"
        artifact_dir.mkdir(parents=True, exist_ok=True)

        session = RuntimeSession(
            session_id=SessionId("session-artifact"),
            routing_key=RoutingKey("key-artifact"),
            lifecycle=SessionLifecycle.IDLE,
            artifact_dir=artifact_dir,
            created_at="2026-04-07T09:00:00Z",
        )

        save_session_state(session, state_root)

        loaded = load_session_state(SessionId("session-artifact"), state_root)
        assert loaded is not None
        assert loaded.artifact_dir == artifact_dir
        assert loaded.artifact_dir.exists()
