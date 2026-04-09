"""Normalized event ingest and label persistence."""

from __future__ import annotations

import json
from typing import Any, Protocol, cast

from core.agent_log_analysis.errors import EventConflictError
from core.agent_log_analysis.store_protocols import StorePoolProtocol

_INSERT_EVENT_SQL = """
INSERT INTO agent_log_events (
    event_id, event_type, occurred_at, received_at, agent_slug,
    run_id, thread_id, correlation_id, parent_event_id,
    status, model_name, provider_name, request_kind,
    action_kind, target_name, target_agent_slug, latency_ms,
    metadata_json, payload_json, raw_payload_attached
) VALUES (
    $1, $2, $3, $4, $5,
    $6, $7, $8, $9,
    $10, $11, $12, $13,
    $14, $15, $16, $17,
    $18, $19, $20
)
"""

_SELECT_EVENT_SQL = """
SELECT payload_json FROM agent_log_events WHERE event_id = $1
"""

_INSERT_LABEL_SQL = """
INSERT INTO agent_log_event_labels (event_id, label_key, label_value)
VALUES ($1, $2, $3)
ON CONFLICT (event_id, label_key) DO UPDATE SET label_value = EXCLUDED.label_value
"""


# Type aliases to keep annotation complexity under WPS234/WPS221 limits
EventRow = dict[str, Any]
LabelMap = dict[str, str]
EventWithLabels = tuple[EventRow, LabelMap]
IngestOutcome = tuple[bool, Exception | None]
BatchResult = list[IngestOutcome]


class IngestStoreMixin:
    """Mixin for normalized event ingest operations."""

    pool: StorePoolProtocol | None

    async def insert_event(
        self,
        event_row: dict[str, Any],
        labels: dict[str, str],
    ) -> bool:
        """Insert a normalized event row with labels.

        Returns True if inserted, False if duplicate.
        Raises EventConflictError if event_id exists with different content.
        """
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            return await _insert_within_conn(
                cast(_WriteConnProtocol, conn),
                event_row,
                labels,
            )

    async def insert_event_batch(
        self,
        rows: list[EventWithLabels],
    ) -> BatchResult:
        """Insert multiple events in one transaction."""
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            return await _run_batch(cast(_WriteConnProtocol, conn), rows)


class _WriteConnProtocol(Protocol):
    async def fetchval(self, query: str, *args: Any) -> Any: ...

    async def execute(self, query: str, *args: Any) -> str: ...

    async def executemany(self, command: str, args: object) -> None: ...

    def transaction(self) -> Any: ...


async def _insert_within_conn(
    conn: _WriteConnProtocol,
    event_row: dict[str, Any],
    labels: dict[str, str],
) -> bool:
    existing = await conn.fetchval(_SELECT_EVENT_SQL, event_row["event_id"])
    if existing is not None:
        return _handle_duplicate(event_row, existing)
    await conn.execute(
        _INSERT_EVENT_SQL,
        event_row["event_id"],
        event_row["event_type"],
        event_row["occurred_at"],
        event_row["received_at"],
        event_row["agent_slug"],
        event_row.get("run_id"),
        event_row.get("thread_id"),
        event_row.get("correlation_id"),
        event_row.get("parent_event_id"),
        event_row.get("status"),
        event_row.get("model_name"),
        event_row.get("provider_name"),
        event_row.get("request_kind"),
        event_row.get("action_kind"),
        event_row.get("target_name"),
        event_row.get("target_agent_slug"),
        event_row.get("latency_ms"),
        event_row.get("metadata_json", {}),
        event_row["payload_json"],
        event_row.get("raw_payload_attached", False),
    )
    await _insert_labels(conn, event_row["event_id"], labels)
    return True


def _handle_duplicate(event_row: dict[str, Any], existing_payload: Any) -> bool:
    incoming_json = json.dumps(event_row["payload_json"], sort_keys=True)
    existing_json = json.dumps(existing_payload, sort_keys=True)
    if incoming_json == existing_json:
        return False
    raise EventConflictError(event_row["event_id"])


async def _run_batch(  # noqa: WPS476 - batch items require sequential per-event duplicate/conflict checks
    conn: _WriteConnProtocol,
    rows: list[EventWithLabels],
) -> BatchResult:
    results: BatchResult = []
    async with conn.transaction():
        for event_row, labels in rows:
            item = await _try_insert_one(conn, event_row, labels)  # noqa: WPS476
            results.append(item)
    return results


async def _try_insert_one(
    conn: _WriteConnProtocol,
    event_row: EventRow,
    labels: LabelMap,
) -> IngestOutcome:
    try:
        inserted = await _insert_within_conn(conn, event_row, labels)
    except EventConflictError as exc:
        return (False, exc)
    return (inserted, None)


async def _insert_labels(
    conn: _WriteConnProtocol,
    event_id: str,
    labels: dict[str, str],
) -> None:
    label_rows = [(event_id, k, lv) for k, lv in labels.items()]
    if label_rows:
        await conn.executemany(_INSERT_LABEL_SQL, label_rows)
