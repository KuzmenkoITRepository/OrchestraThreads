"""Builders for validated raw-log query params."""

from __future__ import annotations

from core.agent_log_analysis import (
    store_raw_logs as raw_log_store,
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
    validation_query_models as query_models,
)
from core.agent_log_analysis import (
    validation_scalars as scalars,
)
from core.agent_log_analysis.api_query_models import AgentRawLogQueryRequest
from core.agent_log_analysis.config import AgentLogAnalysisConfig
from core.agent_log_analysis.validation_query_builders import (
    _validated_limit,
    _validated_window,
)


def build_raw_log_query(
    request: AgentRawLogQueryRequest,
    *,
    config: AgentLogAnalysisConfig,
) -> query_models.ValidatedRawLogQuery:
    """Build validated raw-log query result."""
    window = _validated_window(config, request.window_start, request.window_end)
    limit = _validated_limit(config, request.limit)
    cursor = query_cursors.parse_raw_log_cursor(request.cursor)
    store_params = raw_log_store.RawLogQueryParams(
        agent_slug=query_bounds.require_agent_slug(request.agent_slug),
        since=window[0],
        until=window[1],
        limit=limit,
        cursor_occurred_at=cursor[0],
        cursor_log_id=cursor[1],
        run_id=scalars.optional_text(request.run_id),
        thread_id=scalars.optional_text(request.thread_id),
        correlation_id=scalars.optional_text(request.correlation_id),
    )
    return query_models.ValidatedRawLogQuery(
        store_params=store_params,
        event_id=scalars.optional_text(request.event_id),
        level=query_filters.parse_optional_level(request.level),
        source=scalars.optional_text(request.source),
    )
