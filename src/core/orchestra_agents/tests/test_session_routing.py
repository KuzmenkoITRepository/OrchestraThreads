"""Tests for session routing and concurrency."""

from __future__ import annotations

import threading
from pathlib import Path
from tempfile import TemporaryDirectory

from core.orchestra_agents.agent_mux_runtime.event_types import NormalizedEvent
from core.orchestra_agents.agent_mux_runtime.session_resolver import SessionResolver
from core.orchestra_agents.agent_mux_runtime.session_store import SessionStore
from core.orchestra_agents.agent_mux_runtime.session_types import RoutingKey


class _ConcurrentCreator:
    def __init__(self, resolver: SessionResolver, results: list[str]) -> None:
        self._resolver = resolver
        self._results = results

    def __call__(self) -> None:
        session = self._resolver.resolve_or_create_session(RoutingKey("key-concurrent"))
        self._results.append(session.session_id)


def test_resolve_or_create_session_creates_new() -> None:
    with TemporaryDirectory() as tmpdir:
        state_root = Path(tmpdir)
        session_store = SessionStore(state_root)
        resolver = SessionResolver(session_store, state_root)

        session = resolver.resolve_or_create_session(RoutingKey("key-new"))

        assert session is not None
        assert session.routing_key == "key-new"
        assert session.session_id.startswith("session-")


def test_resolve_or_create_session_reuses_existing() -> None:
    with TemporaryDirectory() as tmpdir:
        state_root = Path(tmpdir)
        session_store = SessionStore(state_root)
        resolver = SessionResolver(session_store, state_root)

        session1 = resolver.resolve_or_create_session(RoutingKey("key-reuse"))
        session2 = resolver.resolve_or_create_session(RoutingKey("key-reuse"))

        assert session1.session_id == session2.session_id


def test_concurrent_same_key_events_reuse_one_session() -> None:
    with TemporaryDirectory() as tmpdir:
        state_root = Path(tmpdir)
        session_store = SessionStore(state_root)
        resolver = SessionResolver(session_store, state_root)

        results: list[str] = []
        target = _ConcurrentCreator(resolver, results)

        pool = [threading.Thread(target=target) for _ in range(5)]
        for t_item in pool:
            t_item.start()
        for t_item in pool:
            t_item.join()

        assert len(set(results)) == 1


def test_different_routing_keys_create_different_sessions() -> None:
    with TemporaryDirectory() as tmpdir:
        state_root = Path(tmpdir)
        session_store = SessionStore(state_root)
        resolver = SessionResolver(session_store, state_root)

        session1 = resolver.resolve_or_create_session(RoutingKey("key-1"))
        session2 = resolver.resolve_or_create_session(RoutingKey("key-2"))

        assert session1.session_id != session2.session_id
        assert session1.routing_key == "key-1"
        assert session2.routing_key == "key-2"


def test_event_enters_one_session_mailbox() -> None:
    with TemporaryDirectory() as tmpdir:
        state_root = Path(tmpdir)
        session_store = SessionStore(state_root)
        resolver = SessionResolver(session_store, state_root)

        session = resolver.resolve_or_create_session(RoutingKey("key-mailbox"))

        event = NormalizedEvent(
            event_id="evt-mailbox",
            source="test",
            routing_key="key-mailbox",
            kind="message",
            payload={},
            created_at="2026-04-07T09:00:00Z",
        )

        session.append_event(event)

        assert len(session.mailbox) == 1
        assert session.mailbox[0].event_id == "evt-mailbox"


def test_duplicate_active_sessions_detected() -> None:
    with TemporaryDirectory() as tmpdir:
        state_root = Path(tmpdir)
        session_store = SessionStore(state_root)
        resolver = SessionResolver(session_store, state_root)

        resolver.resolve_or_create_session(RoutingKey("key-dup"))

        duplicates = resolver.detect_duplicate_sessions(RoutingKey("key-dup"))

        assert len(duplicates) == 0
