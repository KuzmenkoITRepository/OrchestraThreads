"""Runtime-facing deterministic timeline service."""

from __future__ import annotations

from typing import Protocol

from core.agent_log_analysis import event_query_service_support as query_support
from core.agent_log_analysis.api_response_models import TimelinePage
from core.agent_log_analysis.store_query_sql import EventQueryParams


class _TimelineStoreProtocol(Protocol):
    async def query_events(self, params: EventQueryParams) -> list[dict[str, object]]: ...


class TimelineService:
    """Owns agent-scoped deterministic timeline slices."""

    def __init__(self, *, store: _TimelineStoreProtocol) -> None:
        self._store = store

    async def get_agent_timeline(self, params: EventQueryParams) -> TimelinePage:
        """Return one validated, cursor-paginated timeline page."""
        rows = await self._store.query_events(params)
        return TimelinePage(
            agent_slug=params.agent_slug,
            window_start=query_support.serialize_window(params.since),
            window_end=query_support.serialize_window(params.until),
            items=query_support.map_event_rows(rows),
            next_cursor=query_support.build_next_cursor(rows, limit=params.limit),
        )
