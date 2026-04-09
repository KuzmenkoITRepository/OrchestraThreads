"""Raw log persistence and retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.agent_log_analysis.store_protocols import StorePoolProtocol

_INSERT_RAW_LOG_SQL = """
INSERT INTO agent_log_raw_logs (
    event_id, occurred_at, received_at, agent_slug,
    run_id, thread_id, correlation_id, source,
    level, raw_message, raw_payload_json
) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
RETURNING log_id
"""

_DELETE_EXPIRED_SQL = """
DELETE FROM agent_log_raw_logs WHERE occurred_at < $1
"""


@dataclass(frozen=True)
class RawLogQueryParams:
    """Typed parameters for raw log queries."""

    agent_slug: str
    since: datetime
    until: datetime
    limit: int = 50
    cursor_occurred_at: datetime | None = None
    cursor_log_id: int | None = None
    run_id: str | None = None
    thread_id: str | None = None
    correlation_id: str | None = None


class RawLogStoreMixin:
    """Mixin for raw log insert and query operations."""

    pool: StorePoolProtocol | None

    async def insert_raw_log(
        self,
        raw_row: dict[str, Any],
    ) -> int:
        """Insert a single raw log record. Returns the generated log_id."""
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            log_id = await conn.fetchval(
                _INSERT_RAW_LOG_SQL,
                raw_row.get("event_id"),
                raw_row["occurred_at"],
                raw_row["received_at"],
                raw_row["agent_slug"],
                raw_row.get("run_id"),
                raw_row.get("thread_id"),
                raw_row.get("correlation_id"),
                raw_row.get("source"),
                raw_row["level"],
                raw_row["raw_message"],
                raw_row.get("raw_payload_json"),
            )
        return int(log_id)

    async def query_raw_logs(
        self,
        params: RawLogQueryParams,
    ) -> list[dict[str, Any]]:
        """Query raw logs scoped by agent_slug and time window."""
        assert self.pool is not None
        query, values = _build_raw_log_query(params)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *values)
        return [dict(row) for row in rows]

    async def delete_expired_raw_logs(self, cutoff: datetime) -> int:
        """Delete raw logs older than cutoff. Returns count deleted."""
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            cmd = await conn.execute(_DELETE_EXPIRED_SQL, cutoff)
        return _parse_delete_count(cmd)


def _build_raw_log_query(
    params: RawLogQueryParams,
) -> tuple[str, list[Any]]:
    clauses = ["agent_slug = $1", "occurred_at >= $2", "occurred_at <= $3"]
    values: list[Any] = [params.agent_slug, params.since, params.until]
    idx = _append_cursor(clauses, values, params)
    idx = _append_optional(clauses, values, idx, params)
    where = " AND ".join(clauses)
    sql = (
        f"SELECT * FROM agent_log_raw_logs WHERE {where}"  # noqa: S608 - parameterized
        f" ORDER BY occurred_at DESC, log_id DESC LIMIT ${idx}"
    )
    values.append(params.limit)
    return sql, values


def _append_cursor(
    clauses: list[str],
    values: list[Any],
    params: RawLogQueryParams,
) -> int:
    idx = 4
    if params.cursor_occurred_at is not None and params.cursor_log_id is not None:
        clauses.append(f"(occurred_at, log_id) < (${idx}, ${idx + 1})")
        values.extend([params.cursor_occurred_at, params.cursor_log_id])
        idx += 2
    return idx


def _append_optional(
    clauses: list[str],
    values: list[Any],
    idx: int,
    params: RawLogQueryParams,
) -> int:
    for col, col_value in _optional_filters(params):
        clauses.append(f"{col} = ${idx}")
        values.append(col_value)
        idx += 1
    return idx


def _optional_filters(params: RawLogQueryParams) -> list[tuple[str, str]]:
    filters: list[tuple[str, str]] = []
    if params.run_id is not None:
        filters.append(("run_id", params.run_id))
    if params.thread_id is not None:
        filters.append(("thread_id", params.thread_id))
    if params.correlation_id is not None:
        filters.append(("correlation_id", params.correlation_id))
    return filters


def _parse_delete_count(cmd: str) -> int:
    parts = cmd.split()
    if len(parts) >= 2:
        return int(parts[1])
    return 0
