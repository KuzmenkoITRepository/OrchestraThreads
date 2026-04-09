"""Agent-scoped event query and point lookup store."""

from __future__ import annotations

from typing import Any

from core.agent_log_analysis.store_protocols import StorePoolProtocol
from core.agent_log_analysis.store_query_sql import (
    EventQueryParams,
    build_event_query,
)
from core.agent_log_analysis.store_row_helpers import row_to_dict

_SELECT_BY_ID_SQL = """
SELECT * FROM agent_log_events WHERE event_id = $1
"""


class QueryStoreMixin:
    """Mixin for agent-scoped event queries."""

    pool: StorePoolProtocol | None

    async def get_event_by_id(
        self,
        event_id: str,
    ) -> dict[str, Any] | None:
        """Point lookup by event_id."""
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(_SELECT_BY_ID_SQL, event_id)
        return row_to_dict(row)

    async def query_events(
        self,
        params: EventQueryParams,
    ) -> list[dict[str, Any]]:
        """Agent-scoped paginated event query."""
        assert self.pool is not None
        query, values = build_event_query(params)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *values)
        return _rows_to_dicts(rows)


def _rows_to_dicts(rows: list[Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows:
        converted = row_to_dict(row)
        if converted is not None:
            result.append(converted)
    return result
