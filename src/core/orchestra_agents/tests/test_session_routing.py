"""Tests for session routing and concurrency."""

from __future__ import annotations

import threading
from pathlib import Path
from tempfile import TemporaryDirectory

from core.orchestra_agents.backends.agent_mux.internal.event_types import NormalizedEvent
from core.orchestra_agents.backends.agent_mux.internal.session_resolver import SessionResolver
from core.orchestra_agents.backends.agent_mux.internal.session_store import SessionStore
from core.orchestra_agents.backends.agent_mux.internal.session_types import RoutingKey


def _resolve_concurrent_session(resolver: SessionResolver, session_ids: list[str]) -> None:
    session = resolver.resolve_or_create_session(RoutingKey("key-concurrent"))
    session_ids.append(session.session_id)


def _run_concurrent_resolves(state_root: Path, count: int = 5) -> list[str]:
    resolver = SessionResolver(SessionStore(state_root), state_root)
    session_ids: list[str] = []

    pool = [
        threading.Thread(target=_resolve_concurrent_session, args=(resolver, session_ids))
        for _ in range(count)
    ]
    for t_item in pool:
        t_item.start()
    for t_item in pool:
        t_item.join()
    return session_ids


class TestSessionRouting:
    def test_resolve_or_create_creates_new(self) -> None:
        with TemporaryDirectory() as tmpdir:
            state_root = Path(tmpdir)
            resolver = SessionResolver(SessionStore(state_root), state_root)

            session = resolver.resolve_or_create_session(RoutingKey("key-new"))

            assert session is not None
            assert session.routing_key == "key-new"
            assert session.session_id.startswith("session-")

    def test_resolve_session_reuses_existing(self) -> None:
        with TemporaryDirectory() as tmpdir:
            state_root = Path(tmpdir)
            resolver = SessionResolver(SessionStore(state_root), state_root)

            first = resolver.resolve_or_create_session(RoutingKey("key-reuse"))
            second = resolver.resolve_or_create_session(RoutingKey("key-reuse"))

            assert first.session_id == second.session_id

    def test_concurrent_same_key_reuse_session(self) -> None:
        with TemporaryDirectory() as tmpdir:
            resolved_ids = _run_concurrent_resolves(Path(tmpdir))
            assert len(set(resolved_ids)) == 1

    def test_different_keys_create_sessions(self) -> None:
        with TemporaryDirectory() as tmpdir:
            state_root = Path(tmpdir)
            resolver = SessionResolver(SessionStore(state_root), state_root)

            first = resolver.resolve_or_create_session(RoutingKey("key-1"))
            second = resolver.resolve_or_create_session(RoutingKey("key-2"))

            assert first.session_id != second.session_id
            assert first.routing_key == "key-1"
            assert second.routing_key == "key-2"

    def test_event_enters_one_session_mailbox(self) -> None:
        with TemporaryDirectory() as tmpdir:
            state_root = Path(tmpdir)
            resolver = SessionResolver(SessionStore(state_root), state_root)
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

    def test_duplicate_active_sessions_detected(self) -> None:
        with TemporaryDirectory() as tmpdir:
            state_root = Path(tmpdir)
            resolver = SessionResolver(SessionStore(state_root), state_root)

            resolver.resolve_or_create_session(RoutingKey("key-dup"))

            duplicates = resolver.detect_duplicate_sessions(RoutingKey("key-dup"))

            assert len(duplicates) == 0
