"""Typed dependency container for the agent log analysis service."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from core.agent_log_analysis.config import AgentLogAnalysisConfig

if TYPE_CHECKING:
    from core.agent_log_analysis.correlation_service import CorrelationService
    from core.agent_log_analysis.event_query_service import EventQueryService
    from core.agent_log_analysis.ingest_service import IngestService
    from core.agent_log_analysis.raw_log_service import RawLogService
    from core.agent_log_analysis.store import LogStore
    from core.agent_log_analysis.timeline_service import TimelineService
    from core.agent_log_analysis.validation_ingest import IngestValidator
    from core.agent_log_analysis.validation_query import QueryValidator


@dataclass
class ServiceState:
    """Runtime dependency container."""

    config: AgentLogAnalysisConfig
    store: LogStore | None = field(default=None, init=False)
    ingest_validator: IngestValidator | None = field(default=None, init=False)
    query_validator: QueryValidator | None = field(default=None, init=False)
    ingest_service: IngestService | None = field(default=None, init=False)
    event_query_service: EventQueryService | None = field(default=None, init=False)
    timeline_service: TimelineService | None = field(default=None, init=False)
    correlation_service: CorrelationService | None = field(default=None, init=False)
    raw_log_service: RawLogService | None = field(default=None, init=False)
    aggregation_service: object | None = field(default=None, init=False)
    started: bool = field(default=False, init=False)
