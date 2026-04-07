"""Native CLI adapter interface for session persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from core.orchestra_agents.agent_mux_runtime.event_types import NormalizedEvent
from core.orchestra_agents.agent_mux_runtime.session_types import SessionId


class NativeCliAdapter(ABC):
    """
    Interface for native CLI session management.

    Implementations handle CLI-specific session lifecycle:
    - starting new sessions
    - resuming existing sessions
    - stopping sessions
    - resetting session state
    """

    @abstractmethod
    def start_session(
        self, session_id: SessionId, initial_event: NormalizedEvent
    ) -> dict[str, Any]:
        """
        Start a new CLI session.

        Returns CLI session metadata.
        """
        ...

    @abstractmethod
    def resume_session(self, session_id: SessionId, event: NormalizedEvent) -> dict[str, Any]:
        """
        Resume an existing CLI session with a new event.

        Returns execution result.
        """
        ...

    @abstractmethod
    def stop_session(self, session_id: SessionId) -> None:
        """Stop a CLI session."""
        ...

    @abstractmethod
    def reset_session(self, session_id: SessionId) -> None:
        """Reset CLI session state."""
        ...

    @abstractmethod
    def session_exists(self, session_id: SessionId) -> bool:
        """Check if CLI session exists."""
        ...
