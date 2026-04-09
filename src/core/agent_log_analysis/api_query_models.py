"""Query request and response DTOs for agent log analysis."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgentEventQueryRequest:
    """Agent-scoped event query request."""

    agent_slug: str
    window_start: str | None = None
    window_end: str | None = None
    run_id: str | None = None
    thread_id: str | None = None
    correlation_id: str | None = None
    event_type: str | None = None
    status: str | None = None
    request_kind: str | None = None
    action_kind: str | None = None
    target_name: str | None = None
    target_agent_slug: str | None = None
    provider_name: str | None = None
    model_name: str | None = None
    labels: dict[str, str] = field(default_factory=dict)
    cursor: str | None = None
    limit: int | None = None


@dataclass(frozen=True)
class AgentTimelineRequest:
    """Agent-scoped timeline request."""

    agent_slug: str
    window_start: str | None = None
    window_end: str | None = None
    run_id: str | None = None
    thread_id: str | None = None
    cursor: str | None = None
    limit: int | None = None


@dataclass(frozen=True)
class AgentCorrelationRequest:
    """Agent-scoped correlation chain request."""

    agent_slug: str
    correlation_id: str
    run_id: str | None = None
    thread_id: str | None = None


@dataclass(frozen=True)
class AgentAggregateRequest:
    """Agent-scoped aggregation request."""

    agent_slug: str
    window_start: str
    window_end: str
    group_by: list[str] = field(default_factory=list)
    metrics: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AgentRawLogQueryRequest:
    """Agent-scoped raw log query request."""

    agent_slug: str
    window_start: str | None = None
    window_end: str | None = None
    run_id: str | None = None
    thread_id: str | None = None
    correlation_id: str | None = None
    event_id: str | None = None
    level: str | None = None
    source: str | None = None
    cursor: str | None = None
    limit: int | None = None
