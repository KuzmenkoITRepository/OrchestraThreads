"""Bounded correlation chain lookup store."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.agent_log_analysis.store_protocols import StorePoolProtocol
from core.agent_log_analysis.store_row_helpers import row_to_dict


@dataclass(frozen=True)
class CorrelationQueryParams:
    """Typed parameters for correlation chain queries."""

    agent_slug: str
    correlation_id: str
    max_nodes: int = 200
    run_id: str | None = None
    thread_id: str | None = None


class CorrelationStoreMixin:
    """Mixin for bounded correlation chain lookups."""

    pool: StorePoolProtocol | None

    async def query_correlation_chain(
        self,
        params: CorrelationQueryParams,
    ) -> list[dict[str, Any]]:
        """Bounded lookup by agent_slug + correlation_id.

        Returns events ordered by (occurred_at ASC, event_id ASC)
        for chain presentation, capped at max_nodes.
        """
        assert self.pool is not None
        query, values = _build_correlation_query(params)
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


def _build_correlation_query(
    params: CorrelationQueryParams,
) -> tuple[str, list[Any]]:
    clauses = ["agent_slug = $1", "correlation_id = $2"]
    values: list[Any] = [params.agent_slug, params.correlation_id]
    idx = 3
    idx = _append_optional(clauses, values, idx, params)
    where = " AND ".join(clauses)
    sql = (
        f"SELECT * FROM agent_log_events WHERE {where}"  # noqa: S608 - parameterized
        f" ORDER BY occurred_at ASC, event_id ASC LIMIT ${idx}"
    )
    values.append(params.max_nodes)
    return sql, values


def _append_optional(
    clauses: list[str],
    values: list[Any],
    idx: int,
    params: CorrelationQueryParams,
) -> int:
    if params.run_id is not None:
        clauses.append(f"run_id = ${idx}")
        values.append(params.run_id)
        idx += 1
    if params.thread_id is not None:
        clauses.append(f"thread_id = ${idx}")
        values.append(params.thread_id)
        idx += 1
    return idx
