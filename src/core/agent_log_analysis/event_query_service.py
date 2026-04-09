"""Runtime-facing exact lookup and paginated event-query service."""

from __future__ import annotations

from typing import Protocol

from core.agent_log_analysis import event_query_service_support as query_support
from core.agent_log_analysis.api_response_models import EventPage
from core.agent_log_analysis.errors import EventNotFoundError
from core.agent_log_analysis.ingest_service_models import EventLookupResponse
from core.agent_log_analysis.store_query_sql import EventQueryParams


class _QueryStoreProtocol(Protocol):
    async def get_event_by_id(self, event_id: str) -> dict[str, object] | None: ...

    async def query_events(self, params: EventQueryParams) -> list[dict[str, object]]: ...


class EventQueryService:
    """Owns exact event lookup and paginated event queries."""

    def __init__(self, *, store: _QueryStoreProtocol) -> None:
        self._store = store

    async def get_event(self, event_id: str) -> EventLookupResponse:
        """Return one stored event or raise typed not-found."""
        row = await self._store.get_event_by_id(event_id)
        if row is None:
            raise EventNotFoundError(event_id)
        return EventLookupResponse(event=query_support.map_event_row(row))

    async def query_agent_events(self, params: EventQueryParams) -> EventPage:
        """Return one validated, cursor-paginated event page."""
        rows = await self._store.query_events(params)
        return EventPage(
            agent_slug=params.agent_slug,
            window_start=query_support.serialize_window(params.since),
            window_end=query_support.serialize_window(params.until),
            items=query_support.map_event_rows(rows),
            next_cursor=query_support.build_next_cursor(rows, limit=params.limit),
        )
