"""Tests for session types and lifecycle."""

from __future__ import annotations

from core.orchestra_agents.agent_mux_runtime.session_types import (
    RoutingKey,
    SessionId,
    SessionLifecycle,
)


def test_session_lifecycle_states() -> None:
    assert SessionLifecycle.IDLE.value == "idle"
    assert SessionLifecycle.BUSY.value == "busy"
    assert SessionLifecycle.INTERRUPTING.value == "interrupting"
    assert SessionLifecycle.FAILED.value == "failed"
    assert SessionLifecycle.RESETTING.value == "resetting"


def test_session_lifecycle_is_active() -> None:
    assert SessionLifecycle.IDLE.is_active() is True
    assert SessionLifecycle.BUSY.is_active() is True
    assert SessionLifecycle.INTERRUPTING.is_active() is True
    assert SessionLifecycle.FAILED.is_active() is False
    assert SessionLifecycle.RESETTING.is_active() is False


def test_session_lifecycle_is_terminal() -> None:
    assert SessionLifecycle.IDLE.is_terminal() is False
    assert SessionLifecycle.BUSY.is_terminal() is False
    assert SessionLifecycle.INTERRUPTING.is_terminal() is False
    assert SessionLifecycle.FAILED.is_terminal() is True
    assert SessionLifecycle.RESETTING.is_terminal() is False


def test_session_id_type() -> None:
    session_id = SessionId("session-abc123")
    assert isinstance(session_id, str)
    assert session_id == "session-abc123"


def test_routing_key_type() -> None:
    routing_key = RoutingKey("key-xyz789")
    assert isinstance(routing_key, str)
    assert routing_key == "key-xyz789"


def test_no_thread_references_in_types() -> None:
    lifecycle_values = [lc.value for lc in SessionLifecycle]
    assert all("thread" not in lifecycle_val for lifecycle_val in lifecycle_values)
