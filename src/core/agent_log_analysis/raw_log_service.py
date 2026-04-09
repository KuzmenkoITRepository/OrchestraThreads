"""Raw log query service."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Protocol

from core.agent_log_analysis.raw_log_models import RawLogPage
from core.agent_log_analysis.raw_log_service_support import map_raw_log
from core.agent_log_analysis.store_raw_logs import RawLogQueryParams
from core.agent_log_analysis.validation_query_models import ValidatedRawLogQuery
from core.agent_log_analysis.validation_time import parse_timestamp, serialize_timestamp


class _RawLogStoreProtocol(Protocol):
    async def query_raw_logs(
        self,
        params: RawLogQueryParams,
    ) -> list[dict[str, object]]: ...


class RawLogService:
    """Service for raw-log retrieval and narrowing."""

    def __init__(self, store: _RawLogStoreProtocol) -> None:
        self._store = store

    async def get_agent_raw_logs(self, validated: ValidatedRawLogQuery) -> RawLogPage:
        params = validated.store_params
        filtered_rows: list[dict[str, object]] = []
        while len(filtered_rows) < validated.store_params.limit:
            rows = await self._store.query_raw_logs(params)
            if not rows:
                break
            filtered = _apply_filters(rows, validated)
            filtered_rows.extend(
                filtered[: validated.store_params.limit - len(filtered_rows)],
            )
            if len(rows) < params.limit:
                break
            params = replace(
                params,
                cursor_occurred_at=_cursor_time(rows[-1].get("occurred_at")),
                cursor_log_id=_cursor_log_id(rows[-1]),
            )
        return RawLogPage(
            agent_slug=validated.store_params.agent_slug,
            items=[map_raw_log(row) for row in filtered_rows],
            next_cursor=build_next_cursor(
                filtered_rows,
                limit=validated.store_params.limit,
            ),
        )


def _apply_filters(
    rows: list[dict[str, object]],
    validated: ValidatedRawLogQuery,
) -> list[dict[str, object]]:
    result = rows
    if validated.event_id is not None:
        result = [row for row in result if row.get("event_id") == validated.event_id]
    if validated.level is not None:
        result = [row for row in result if row.get("level") == validated.level.value]
    if validated.source is not None:
        result = [row for row in result if row.get("source") == validated.source]
    return result


def build_next_cursor(rows: list[dict[str, object]], *, limit: int) -> str | None:
    """Build the stable raw-log page cursor."""
    if not rows or len(rows) < limit:
        return None
    return _cursor_value(rows[-1])


def _cursor_value(last_row: dict[str, object]) -> str:
    occurred_at = serialize_timestamp(_cursor_time(last_row.get("occurred_at")))
    return f"{occurred_at}|{_cursor_log_id(last_row)}"


def _cursor_time(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    return parse_timestamp(value, field_name="occurred_at")


def _cursor_log_id(last_row: dict[str, object]) -> int:
    value = last_row.get("log_id")
    return int(value) if isinstance(value, int) else 0
