"""Session types and lifecycle states for event-centric session routing."""

from __future__ import annotations

from enum import StrEnum
from typing import NewType

SessionId = NewType("SessionId", str)
RoutingKey = NewType("RoutingKey", str)


class SessionLifecycle(StrEnum):
    """Session lifecycle states."""

    IDLE = "idle"
    BUSY = "busy"
    INTERRUPTING = "interrupting"
    FAILED = "failed"
    RESETTING = "resetting"

    def is_active(self) -> bool:
        """Check if session is in an active state."""
        return self in (SessionLifecycle.IDLE, SessionLifecycle.BUSY, SessionLifecycle.INTERRUPTING)

    def is_terminal(self) -> bool:
        """Check if session is in a terminal state."""
        return self == SessionLifecycle.FAILED
