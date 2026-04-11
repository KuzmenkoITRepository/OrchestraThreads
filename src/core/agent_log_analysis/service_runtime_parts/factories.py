"""Factory helpers for agent log analysis runtime dependencies."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, cast

from core.agent_log_analysis import service_state, store, validation_ingest, validation_query

if TYPE_CHECKING:
    from core.agent_log_analysis.aggregation_service import AggregationService
    from core.agent_log_analysis.correlation_service import CorrelationService
    from core.agent_log_analysis.event_query_service import EventQueryService
    from core.agent_log_analysis.ingest_service import IngestService
    from core.agent_log_analysis.raw_log_service import RawLogService
    from core.agent_log_analysis.timeline_service import TimelineService


def build_runtime_dependencies(
    state: service_state.ServiceState,
    log_store: store.LogStore,
) -> None:
    """Bind validators and service adapters to the mutable runtime state."""
    state.store = log_store
    state.ingest_validator = validation_ingest.IngestValidator(state.config)
    state.query_validator = validation_query.QueryValidator(state.config)
    state.ingest_service = _build_ingest_service(state, log_store)
    state.event_query_service = _build_event_query_service(log_store)
    state.timeline_service = _build_timeline_service(log_store)
    state.correlation_service = _build_correlation_service(log_store)
    state.raw_log_service = _build_raw_log_service(log_store)
    state.aggregation_service = _build_aggregation_service(log_store)


def _build_ingest_service(
    state: service_state.ServiceState,
    log_store: store.LogStore,
) -> IngestService:
    return cast(
        "IngestService",
        import_module("core.agent_log_analysis.ingest_service").IngestService(
            store=log_store,
            validator=state.ingest_validator,
        ),
    )


def _build_event_query_service(log_store: store.LogStore) -> EventQueryService:
    return cast(
        "EventQueryService",
        import_module("core.agent_log_analysis.event_query_service").EventQueryService(
            store=log_store,
        ),
    )


def _build_timeline_service(log_store: store.LogStore) -> TimelineService:
    return cast(
        "TimelineService",
        import_module("core.agent_log_analysis.timeline_service").TimelineService(
            store=log_store,
        ),
    )


def _build_correlation_service(log_store: store.LogStore) -> CorrelationService:
    return cast(
        "CorrelationService",
        import_module("core.agent_log_analysis.correlation_service").CorrelationService(
            store=log_store,
        ),
    )


def _build_raw_log_service(log_store: store.LogStore) -> RawLogService:
    return cast(
        "RawLogService",
        import_module("core.agent_log_analysis.raw_log_service").RawLogService(
            store=log_store,
        ),
    )


def _build_aggregation_service(log_store: store.LogStore) -> AggregationService:
    return cast(
        "AggregationService",
        import_module("core.agent_log_analysis.aggregation_service").AggregationService(
            store=log_store,
        ),
    )
