"""Session resolver for atomic session resolution and creation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING

from core.orchestra_agents.backends.agent_mux.internal.session_state import (
    RuntimeSession,
    save_session_state,
)
from core.orchestra_agents.backends.agent_mux.internal.session_types import (
    RoutingKey,
    SessionId,
    SessionLifecycle,
)

if TYPE_CHECKING:
    from core.orchestra_agents.backends.agent_mux.internal.session_store import SessionStore


class SessionResolver:
    """
    Atomic session resolution and creation.

    Guarantees:
    - resolve_active_session(routing_key) returns at most one active session
    - resolve_or_create_session(routing_key) is atomic
    - duplicate active sessions trigger corruption repair
    """

    def __init__(self, session_store: SessionStore, state_root: Path) -> None:
        self._session_store = session_store
        self._state_root = state_root
        self._lock = Lock()

    def resolve_active_session(self, routing_key: RoutingKey) -> RuntimeSession | None:
        """
        Resolve active session for routing key.

        Returns at most one active session.
        If multiple active sessions exist, triggers corruption repair.
        """
        sessions = self._session_store.get_sessions_by_routing_key(routing_key)
        active_sessions = [s for s in sessions if s.lifecycle.is_active()]

        if len(active_sessions) == 0:
            return None
        if len(active_sessions) == 1:
            return active_sessions[0]

        # Corruption detected: multiple active sessions for one routing key
        return self._repair_duplicate_sessions(routing_key, active_sessions)

    def resolve_or_create_session(self, routing_key: RoutingKey) -> RuntimeSession:
        """
        Atomically resolve or create session for routing key.

        If no active session exists, creates a new one.
        """
        with self._lock:
            existing = self.resolve_active_session(routing_key)
            if existing is not None:
                return existing

            # Create new session
            session_id = SessionId(f"session-{uuid.uuid4().hex[:16]}")
            now = datetime.now(UTC).isoformat()
            artifact_dir = self._state_root / "sessions" / session_id / "artifacts"
            artifact_dir.mkdir(parents=True, exist_ok=True)

            session = RuntimeSession(
                session_id=session_id,
                routing_key=routing_key,
                lifecycle=SessionLifecycle.IDLE,
                artifact_dir=artifact_dir,
                created_at=now,
                updated_at=now,
            )

            save_session_state(session, self._state_root)
            self._session_store.register_session(session)
            session.add_timeline_entry("session_created", {"routing_key": routing_key})

            return session

    def detect_duplicate_sessions(self, routing_key: RoutingKey) -> list[RuntimeSession]:
        """Detect duplicate active sessions for a routing key."""
        sessions = self._session_store.get_sessions_by_routing_key(routing_key)
        active_sessions = [s for s in sessions if s.lifecycle.is_active()]
        return active_sessions if len(active_sessions) > 1 else []

    def _repair_duplicate_sessions(
        self,
        routing_key: RoutingKey,
        active_sessions: list[RuntimeSession],
    ) -> RuntimeSession:
        """
        Repair duplicate active sessions.

        Strategy: keep the most recently updated session, mark others as failed.
        """
        # Sort by updated_at descending
        sorted_sessions = sorted(active_sessions, key=lambda s: s.updated_at, reverse=True)
        primary = sorted_sessions[0]
        duplicates = sorted_sessions[1:]

        for dup in duplicates:
            dup.lifecycle = SessionLifecycle.FAILED
            dup.add_timeline_entry(
                "corruption_repair",
                {"reason": "duplicate_active_session", "kept_session": primary.session_id},
            )
            save_session_state(dup, self._state_root)

        primary.add_timeline_entry(
            "corruption_repair",
            {
                "reason": "duplicate_active_session_detected",
                "failed_sessions": [d.session_id for d in duplicates],
            },
        )
        save_session_state(primary, self._state_root)

        return primary
