"""Typed ingest validation results."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.agent_log_analysis.api_models import IngestEventRequest
from core.agent_log_analysis.event_envelope import EventType


@dataclass(frozen=True)
class ValidatedIngestEvent:
    """Validated single-event ingest payload."""

    request: IngestEventRequest
    occurred_at: datetime
    event_type: EventType
    index: int | None = None


@dataclass(frozen=True)
class BatchItemError:
    """Per-item batch validation error."""

    index: int
    error_code: str
    message: str


@dataclass(frozen=True)
class BatchValidationResult:
    """Validated batch payload with partial-success errors."""

    events: list[ValidatedIngestEvent]
    errors: list[BatchItemError]
