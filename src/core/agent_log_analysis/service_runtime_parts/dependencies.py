"""Lifecycle helpers for the agent log analysis runtime."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any, cast

from core.agent_log_analysis import service_state

if TYPE_CHECKING:
    from core.agent_log_analysis.store import LogStore


async def start_service_state(state: service_state.ServiceState) -> None:
    """Create and bind runtime dependencies to the mutable service state."""
    log_store = _build_store(state)
    await log_store.start()
    factories = import_module("core.agent_log_analysis.service_runtime_parts.factories")
    cast(Any, factories).build_runtime_dependencies(state, log_store)
    state.started = True


async def stop_service_state(state: service_state.ServiceState) -> None:
    """Close and clear runtime dependencies from the mutable service state."""
    if state.store is not None:
        await state.store.close()
    _clear_runtime_dependencies(state)


def _clear_runtime_dependencies(state: service_state.ServiceState) -> None:
    state.store = None
    state.ingest_validator = None
    state.query_validator = None
    state.ingest_service = None
    state.event_query_service = None
    state.timeline_service = None
    state.correlation_service = None
    state.raw_log_service = None
    state.aggregation_service = None
    state.started = False


def _build_store(state: service_state.ServiceState) -> LogStore:
    config = state.config
    store_module = import_module("core.agent_log_analysis.store")
    return cast(
        "LogStore",
        cast(Any, store_module).LogStore(
            database_url=config.database_url,
            schema_name=config.db_schema,
        ),
    )
