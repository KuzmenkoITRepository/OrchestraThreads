"""Runtime-facing ingest operations for normalized events."""

from __future__ import annotations

from typing import Protocol

from core.agent_log_analysis import ingest_service_support as support
from core.agent_log_analysis.api_models import IngestEventResult
from core.agent_log_analysis.ingest_service_event_rows import build_event_row
from core.agent_log_analysis.ingest_service_models import (
    BatchIngestResult,
    IngestResponse,
)
from core.agent_log_analysis.validation_ingest import IngestValidator
from core.agent_log_analysis.validation_ingest_models import BatchItemError, ValidatedIngestEvent


class _IngestStoreProtocol(Protocol):
    async def insert_event(
        self,
        event_row: support.EventRow,
        labels: support.LabelMap,
    ) -> bool: ...

    async def insert_raw_log(self, raw_row: support.RawLogRow) -> int: ...


class IngestService:
    """Owns validated ingest flow and point event lookup."""

    def __init__(self, *, store: _IngestStoreProtocol, validator: IngestValidator) -> None:
        self._store = store
        self._validator = validator

    async def ingest_event(self, payload: object) -> IngestResponse:
        """Validate and persist one event payload."""
        validated = self._validator.validate_event(payload)
        result = await self._persist_event(validated)
        return IngestResponse(result=result)

    async def ingest_batch(self, payload: object) -> BatchIngestResult:
        """Validate and persist one batch while preserving input order."""
        validation = self._validator.validate_batch(payload)
        items = await self._persist_batch(validation.events, validation.errors)
        return BatchIngestResult(items=items)

    async def _persist_event(self, validated: ValidatedIngestEvent) -> IngestEventResult:
        stamped_at = support.now_utc()
        event_row = build_event_row(validated.request, received_at=stamped_at)
        inserted = await self._store.insert_event(event_row, validated.request.labels)
        if inserted:
            await support.persist_raw_logs(
                self._store.insert_raw_log,
                validated,
                received_at=stamped_at,
            )
            return IngestEventResult(event_id=validated.request.event_id, status="ok")
        return IngestEventResult(
            event_id=validated.request.event_id,
            status="ok",
            duplicate=True,
        )

    async def _persist_batch(
        self,
        events: list[ValidatedIngestEvent],
        errors: list[BatchItemError],
    ) -> list[IngestEventResult]:
        results = [support.error_result(item) for item in errors]
        for insert_at, result in await support.persist_batch_results(self._persist_event, events):
            results.insert(insert_at, result)
        return results
