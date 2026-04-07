"""Session registry for tracking active runtime sessions."""

from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING

from core.orchestra_agents.agent_mux_runtime.session_state import load_session_state
from core.orchestra_agents.agent_mux_runtime.session_types import RoutingKey, SessionId

if TYPE_CHECKING:
    from core.orchestra_agents.agent_mux_runtime.session_state import RuntimeSession


class SessionStore:
    """
    Session registry mapping routing_key -> session_id.

    Maintains in-memory index and persistent state.
    """

    def __init__(self, state_root: Path) -> None:
        self._state_root = state_root
        self._routing_key_index: dict[RoutingKey, SessionId] = {}
        self._sessions: dict[SessionId, RuntimeSession] = {}
        self._lock = Lock()
        self._load_existing_sessions()

    def get_active_sessions(self) -> list[RuntimeSession]:
        """Get all active sessions."""
        with self._lock:
            return [s for s in self._sessions.values() if s.lifecycle.is_active()]

    def get_session_by_routing_key(self, routing_key: RoutingKey) -> RuntimeSession | None:
        """Get session by routing key."""
        with self._lock:
            session_id = self._routing_key_index.get(routing_key)
            if session_id is None:
                return None
            return self._sessions.get(session_id)

    def get_sessions_by_routing_key(self, routing_key: RoutingKey) -> list[RuntimeSession]:
        """Get all sessions (including inactive) for a routing key."""
        with self._lock:
            return [s for s in self._sessions.values() if s.routing_key == routing_key]

    def register_session(self, session: RuntimeSession) -> None:
        """Register or update a session in the registry."""
        with self._lock:
            self._sessions[session.session_id] = session
            if session.lifecycle.is_active():
                self._routing_key_index[session.routing_key] = session.session_id
            else:
                self._routing_key_index.pop(session.routing_key, None)

    def _load_existing_sessions(self) -> None:
        """Load existing sessions from persistent storage."""
        sessions_dir = self._state_root / "sessions"
        if not sessions_dir.exists():
            return

        for session_dir in sessions_dir.iterdir():
            if not session_dir.is_dir():
                continue
            session_id = SessionId(session_dir.name)
            session = load_session_state(session_id, self._state_root)
            if session is not None:
                self._sessions[session_id] = session
                if session.lifecycle.is_active():
                    self._routing_key_index[session.routing_key] = session_id
