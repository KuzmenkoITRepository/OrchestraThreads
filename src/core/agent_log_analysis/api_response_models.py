"""Response DTOs for agent log analysis queries."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.agent_log_analysis.api_models import GetEventResult


@dataclass(frozen=True)
class EventPage:
    """Paginated event query response."""

    agent_slug: str
    window_start: str
    window_end: str
    items: list[GetEventResult]
    next_cursor: str | None = None


@dataclass(frozen=True)
class TimelinePage:
    """Paginated timeline response."""

    agent_slug: str
    window_start: str
    window_end: str
    items: list[GetEventResult]
    next_cursor: str | None = None


@dataclass(frozen=True)
class CorrelationChain:
    """Correlation chain response."""

    agent_slug: str
    correlation_id: str
    items: list[GetEventResult]
    truncated: bool = False


@dataclass(frozen=True)
class AggregationBucket:
    """One aggregation bucket."""

    keys: dict[str, str | None]
    count: int = 0
    success_count: int = 0
    error_count: int = 0
    avg_latency_ms: float | None = None


@dataclass(frozen=True)
class AggregationResult:
    """Aggregation query response."""

    agent_slug: str
    window_start: str
    window_end: str
    group_by: list[str]
    metrics: list[str]
    buckets: list[AggregationBucket] = field(default_factory=list)
