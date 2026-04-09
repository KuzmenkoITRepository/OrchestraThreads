"""Domain error types for the agent log analysis service."""

from __future__ import annotations


class AgentLogAnalysisError(Exception):
    """Base error for agent log analysis service."""


class ConfigError(AgentLogAnalysisError):
    """Configuration error."""


class ValidationError(AgentLogAnalysisError):
    """Request validation error."""

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message


class StoreError(AgentLogAnalysisError):
    """Storage layer error."""


class EventConflictError(StoreError):
    """Raised when event_id replay has conflicting content."""

    def __init__(self, event_id: str) -> None:
        super().__init__(f"EVENT_ID_CONFLICT: {event_id}")
        self.event_id = event_id


class EventNotFoundError(StoreError):
    """Raised when an event lookup misses."""

    def __init__(self, event_id: str) -> None:
        super().__init__(f"EVENT_NOT_FOUND: {event_id}")
        self.event_id = event_id
