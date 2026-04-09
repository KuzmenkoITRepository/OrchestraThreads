"""Action-specific normalized fields for agent telemetry."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ActionKind(StrEnum):
    """Kind of agent action."""

    tool_call = "tool_call"
    message_send = "message_send"
    http_request = "http_request"
    state_transition = "state_transition"
    task_update = "task_update"
    other = "other"


class ActionStatus(StrEnum):
    """Status of an agent action."""

    success = "success"
    error = "error"
    timeout = "timeout"
    cancelled = "cancelled"
    rejected = "rejected"


@dataclass(frozen=True)
class ActionPayload:
    """Normalized action-specific fields."""

    action_kind: ActionKind | None = None
    target_name: str | None = None
    target_agent_slug: str | None = None
    status: ActionStatus | None = None
    latency_ms: int | None = None
    error_message: str | None = None
