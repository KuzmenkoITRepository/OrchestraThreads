"""Typed DTOs for ingest-service responses."""

from __future__ import annotations

from dataclasses import dataclass

from core.agent_log_analysis.api_models import GetEventResult, IngestEventResult


@dataclass(frozen=True)
class BatchIngestResult:
    """Ordered per-item batch ingest response."""

    items: list[IngestEventResult]


@dataclass(frozen=True)
class IngestResponse:
    """Single-event ingest response wrapper."""

    result: IngestEventResult


@dataclass(frozen=True)
class EventLookupResponse:
    """Point event lookup response wrapper."""

    event: GetEventResult
