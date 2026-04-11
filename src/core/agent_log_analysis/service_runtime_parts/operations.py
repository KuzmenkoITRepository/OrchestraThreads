"""Runtime-facing service operations for agent log analysis."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, cast

from core.agent_log_analysis import service_state


class IngestOperations:
    """Mixin exposing ingest-related service methods."""

    state: service_state.ServiceState

    async def ingest_event(
        self,
        payload: object,
        *,
        authorization: str | None,
    ) -> dict[str, object]:
        ingest_service = self.state.ingest_service
        query_validator = self.state.query_validator
        if ingest_service is None or query_validator is None:
            raise service_not_started()
        query_validator.validate_ingest_auth(authorization)
        response = await ingest_service.ingest_event(payload)
        return {"result": asdict(response.result)}

    async def ingest_batch(
        self,
        payload: object,
        *,
        authorization: str | None,
    ) -> dict[str, object]:
        ingest_service = self.state.ingest_service
        query_validator = self.state.query_validator
        if ingest_service is None or query_validator is None:
            raise service_not_started()
        query_validator.validate_ingest_auth(authorization)
        response = await ingest_service.ingest_batch(payload)
        return {"items": [asdict(item) for item in response.items]}


class QueryOperations:
    """Mixin exposing read/query service methods."""

    state: service_state.ServiceState

    async def get_event(self, event_id: str) -> dict[str, object]:
        event_query_service = self.state.event_query_service
        if event_query_service is None:
            raise service_not_started()
        response = await event_query_service.get_event(event_id)
        return {"event": asdict(response.event)}

    async def query_agent_events(self, payload: object) -> dict[str, object]:
        event_query_service = self.state.event_query_service
        query_validator = self.state.query_validator
        if event_query_service is None or query_validator is None:
            raise service_not_started()
        params = query_validator.validate_event_query(payload)
        page = await event_query_service.query_agent_events(params)
        return asdict(page)

    async def get_agent_timeline(self, payload: object) -> dict[str, object]:
        timeline_service = self.state.timeline_service
        query_validator = self.state.query_validator
        if timeline_service is None or query_validator is None:
            raise service_not_started()
        params = query_validator.validate_timeline_query(payload)
        page = await timeline_service.get_agent_timeline(params)
        return asdict(page)

    async def get_agent_correlation_chain(self, payload: object) -> dict[str, object]:
        corr_service = self.state.correlation_service
        query_validator = self.state.query_validator
        if corr_service is None or query_validator is None:
            raise service_not_started()
        params = query_validator.validate_correlation_query(payload)
        chain = await corr_service.get_agent_correlation_chain(params)
        return asdict(chain)

    async def get_agent_raw_logs(self, payload: object) -> dict[str, object]:
        logs_service = self.state.raw_log_service
        query_validator = self.state.query_validator
        if logs_service is None or query_validator is None:
            raise service_not_started()
        params = query_validator.validate_raw_log_query(payload)
        page = await logs_service.get_agent_raw_logs(params)
        return asdict(page)

    async def aggregate_agent_events(self, payload: object) -> dict[str, object]:
        agg_service = self.state.aggregation_service
        query_validator = self.state.query_validator
        if agg_service is None or query_validator is None:
            raise service_not_started()
        params = query_validator.validate_aggregate_query(payload)
        result = await cast(Any, agg_service).aggregate_agent_events(params)
        return asdict(result)


def service_not_started() -> RuntimeError:
    """Build the stable runtime-not-started error."""

    return RuntimeError("service is not started")
