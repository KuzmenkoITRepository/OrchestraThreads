"""Correlation chain service."""

from __future__ import annotations

from typing import Protocol

from core.agent_log_analysis.api_response_models import CorrelationChain
from core.agent_log_analysis.event_query_service_support import map_event_rows
from core.agent_log_analysis.store_correlation import CorrelationQueryParams


class _CorrelationStoreProtocol(Protocol):
    async def query_correlation_chain(
        self,
        params: CorrelationQueryParams,
    ) -> list[dict[str, object]]: ...


class CorrelationService:
    """Service for correlation-chain retrieval."""

    def __init__(self, store: _CorrelationStoreProtocol) -> None:
        self._store = store

    async def get_agent_correlation_chain(
        self,
        params: CorrelationQueryParams,
    ) -> CorrelationChain:
        rows = await self._store.query_correlation_chain(params)
        return CorrelationChain(
            agent_slug=params.agent_slug,
            correlation_id=params.correlation_id,
            items=map_event_rows(rows),
            truncated=len(rows) == params.max_nodes,
        )
