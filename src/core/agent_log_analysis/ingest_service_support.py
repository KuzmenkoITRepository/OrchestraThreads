"""Support helpers for ingest-service persistence flow."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from core.agent_log_analysis.api_models import IngestEventResult
from core.agent_log_analysis.errors import EventConflictError
from core.agent_log_analysis.ingest_service_raw_rows import build_raw_log_rows
from core.agent_log_analysis.validation_ingest_models import ValidatedIngestEvent

EventRow = dict[str, object]
LabelMap = dict[str, str]
RawLogRow = dict[str, object]
PersistEvent = Callable[[ValidatedIngestEvent], Awaitable[IngestEventResult]]


async def persist_raw_logs(
    insert_raw_log: Callable[[RawLogRow], Awaitable[int]],
    validated: ValidatedIngestEvent,
    *,
    received_at: datetime,
) -> None:
    """Persist all raw logs for one validated event."""
    raw_rows = build_raw_log_rows(validated.request, received_at=received_at)
    await _insert_raw_log_rows(insert_raw_log, raw_rows)


async def persist_batch_results(
    persist_event: PersistEvent,
    events: list[ValidatedIngestEvent],
) -> list[tuple[int, IngestEventResult]]:
    """Persist validated batch items while preserving indexes."""
    if not events:
        return []
    head = events[0]
    tail = events[1:]
    result = await _persist_one_batch_item(persist_event, head)
    rest = await persist_batch_results(persist_event, tail)
    insert_at = 0 if head.index is None else head.index
    return [(insert_at, result), *rest]


def error_result(item: object) -> IngestEventResult:
    """Map a batch validation error object into API result shape."""
    index = getattr(item, "index", None)
    return IngestEventResult(
        event_id=f"batch-index-{index}",
        status="error",
        error_code=str(getattr(item, "error_code", "VALIDATION_ERROR")),
        error_message=str(getattr(item, "message", "validation failed")),
    )


def now_utc() -> datetime:
    """Return current UTC timestamp."""
    return datetime.now(tz=UTC)


async def _insert_raw_log_rows(
    insert_raw_log: Callable[[RawLogRow], Awaitable[int]],
    raw_rows: list[RawLogRow],
) -> None:
    if not raw_rows:
        return
    await insert_raw_log(raw_rows[0])
    await _insert_raw_log_rows(insert_raw_log, raw_rows[1:])


async def _persist_one_batch_item(
    persist_event: PersistEvent,
    validated: ValidatedIngestEvent,
) -> IngestEventResult:
    try:
        return await persist_event(validated)
    except EventConflictError as err:
        return IngestEventResult(
            event_id=validated.request.event_id,
            status="error",
            error_code="EVENT_ID_CONFLICT",
            error_message=str(err),
        )
