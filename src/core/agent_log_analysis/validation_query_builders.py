"""Builders for validated analytical query params."""

from __future__ import annotations

from datetime import datetime

from core.agent_log_analysis import (
    store_aggregates as aggregate_store,
)
from core.agent_log_analysis import (
    store_correlation as correlation_store,
)
from core.agent_log_analysis import (
    store_query_sql as query_store,
)
from core.agent_log_analysis import (
    validation_query_bounds as query_bounds,
)
from core.agent_log_analysis import (
    validation_query_cursors as query_cursors,
)
from core.agent_log_analysis import (
    validation_query_filters as query_filters,
)
from core.agent_log_analysis import (
    validation_scalars as scalars,
)
from core.agent_log_analysis.api_query_models import (
    AgentAggregateRequest,
    AgentCorrelationRequest,
    AgentEventQueryRequest,
    AgentTimelineRequest,
)
from core.agent_log_analysis.config import AgentLogAnalysisConfig


def build_event_query_params(
    request: AgentEventQueryRequest,
    *,
    config: AgentLogAnalysisConfig,
) -> query_store.EventQueryParams:
    """Build validated event-query params."""
    window = _validated_window(config, request.window_start, request.window_end)
    limit = _validated_limit(config, request.limit)
    cursor = query_cursors.parse_event_cursor(request.cursor)
    return query_store.EventQueryParams(
        agent_slug=query_bounds.require_agent_slug(request.agent_slug),
        since=window[0],
        until=window[1],
        limit=limit,
        cursor_occurred_at=cursor[0],
        cursor_event_id=cursor[1],
        filters=query_filters.build_event_filters(request),
        label_filters=query_filters.normalize_labels(request.labels),
    )


def build_timeline_query_params(
    request: AgentTimelineRequest,
    *,
    config: AgentLogAnalysisConfig,
) -> query_store.EventQueryParams:
    """Build validated timeline-query params."""
    window = _validated_window(config, request.window_start, request.window_end)
    limit = _validated_limit(config, request.limit)
    cursor = query_cursors.parse_event_cursor(request.cursor)
    return query_store.EventQueryParams(
        agent_slug=query_bounds.require_agent_slug(request.agent_slug),
        since=window[0],
        until=window[1],
        limit=limit,
        cursor_occurred_at=cursor[0],
        cursor_event_id=cursor[1],
        filters=query_filters.build_timeline_filters(
            run_id=request.run_id,
            thread_id=request.thread_id,
        ),
    )


def build_correlation_query_params(
    request: AgentCorrelationRequest,
    *,
    config: AgentLogAnalysisConfig,
) -> correlation_store.CorrelationQueryParams:
    """Build validated correlation-query params."""
    return correlation_store.CorrelationQueryParams(
        agent_slug=query_bounds.require_agent_slug(request.agent_slug),
        correlation_id=scalars.required_text(
            request.correlation_id,
            field_name="correlation_id",
        ),
        max_nodes=config.max_correlation_nodes,
        run_id=scalars.optional_text(request.run_id),
        thread_id=scalars.optional_text(request.thread_id),
    )


def build_aggregate_query_params(
    request: AgentAggregateRequest,
    *,
    config: AgentLogAnalysisConfig,
) -> aggregate_store.AggregateQueryParams:
    """Build validated aggregate-query params."""
    window = _validated_window(config, request.window_start, request.window_end)
    return aggregate_store.AggregateQueryParams(
        agent_slug=query_bounds.require_agent_slug(request.agent_slug),
        since=window[0],
        until=window[1],
        group_by=query_filters.normalize_group_by(
            request.group_by,
            max_group_keys=config.max_aggregation_group_keys,
        ),
        metrics=query_filters.normalize_metrics(request.metrics),
    )


def _validated_window(
    config: AgentLogAnalysisConfig,
    window_start: str | None,
    window_end: str | None,
) -> tuple[datetime, datetime]:
    return query_bounds.resolve_window(
        window_start,
        window_end,
        query_window_hours=config.query_window_hours,
    )


def _validated_limit(config: AgentLogAnalysisConfig, limit: int | None) -> int:
    return query_bounds.resolve_limit(
        limit,
        default_limit=config.query_page_default,
        max_limit=config.query_page_max,
    )
