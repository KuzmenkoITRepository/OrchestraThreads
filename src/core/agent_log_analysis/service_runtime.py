"""HTTP runtime for the agent log analysis service."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from importlib import import_module
from typing import Any, cast

from aiohttp import web

from core.agent_log_analysis import config as log_config
from core.agent_log_analysis import service_state, store, validation_ingest, validation_query

logger = logging.getLogger(__name__)
SERVICE_APP_KEY: web.AppKey[AgentLogAnalysisService] = web.AppKey("AgentLogAnalysisService")


class _ServiceOperations:
    """Runtime-facing service operations."""

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
            raise _service_not_started()
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
            raise _service_not_started()
        query_validator.validate_ingest_auth(authorization)
        response = await ingest_service.ingest_batch(payload)
        return {"items": [asdict(item) for item in response.items]}

    async def get_event(self, event_id: str) -> dict[str, object]:
        event_query_service = self.state.event_query_service
        if event_query_service is None:
            raise _service_not_started()
        response = await event_query_service.get_event(event_id)
        return {"event": asdict(response.event)}

    async def query_agent_events(self, payload: object) -> dict[str, object]:
        event_query_service = self.state.event_query_service
        query_validator = self.state.query_validator
        if event_query_service is None or query_validator is None:
            raise _service_not_started()
        params = query_validator.validate_event_query(payload)
        page = await event_query_service.query_agent_events(params)
        return asdict(page)

    async def get_agent_timeline(self, payload: object) -> dict[str, object]:
        timeline_service = self.state.timeline_service
        query_validator = self.state.query_validator
        if timeline_service is None or query_validator is None:
            raise _service_not_started()
        params = query_validator.validate_timeline_query(payload)
        page = await timeline_service.get_agent_timeline(params)
        return asdict(page)

    async def get_agent_correlation_chain(self, payload: object) -> dict[str, object]:
        corr_service = self.state.correlation_service
        query_validator = self.state.query_validator
        if corr_service is None or query_validator is None:
            raise _service_not_started()
        params = query_validator.validate_correlation_query(payload)
        chain = await corr_service.get_agent_correlation_chain(params)
        return asdict(chain)

    async def get_agent_raw_logs(self, payload: object) -> dict[str, object]:
        logs_service = self.state.raw_log_service
        query_validator = self.state.query_validator
        if logs_service is None or query_validator is None:
            raise _service_not_started()
        params = query_validator.validate_raw_log_query(payload)
        page = await logs_service.get_agent_raw_logs(params)
        return asdict(page)


class AgentLogAnalysisService(_ServiceOperations):
    """Agent log analysis HTTP service."""

    def __init__(self, config: log_config.AgentLogAnalysisConfig | None = None) -> None:
        self.config = config or log_config.load_config()
        self.state = service_state.ServiceState(config=self.config)

    async def start(self) -> None:
        if self.state.started:
            return
        log_store = store.LogStore(
            database_url=self.config.database_url,
            schema_name=self.config.db_schema,
        )
        await log_store.start()
        self.state.store = log_store
        self.state.ingest_validator = validation_ingest.IngestValidator(self.config)
        self.state.query_validator = validation_query.QueryValidator(self.config)
        self.state.ingest_service = cast(
            Any,
            import_module("core.agent_log_analysis.ingest_service").IngestService(
                store=log_store,
                validator=self.state.ingest_validator,
            ),
        )
        self.state.event_query_service = cast(
            Any,
            import_module("core.agent_log_analysis.event_query_service").EventQueryService(
                store=log_store,
            ),
        )
        self.state.timeline_service = cast(
            Any,
            import_module("core.agent_log_analysis.timeline_service").TimelineService(
                store=log_store,
            ),
        )
        self.state.correlation_service = cast(
            Any,
            import_module("core.agent_log_analysis.correlation_service").CorrelationService(
                store=log_store,
            ),
        )
        self.state.raw_log_service = cast(
            Any,
            import_module("core.agent_log_analysis.raw_log_service").RawLogService(
                store=log_store,
            ),
        )
        self.state.aggregation_service = cast(
            Any,
            import_module("core.agent_log_analysis.aggregation_service").AggregationService(
                store=log_store,
            ),
        )
        self.state.started = True

    async def stop(self) -> None:
        if not self.state.started:
            return
        if self.state.store is not None:
            await self.state.store.close()
        self.state.store = None
        self.state.ingest_validator = None
        self.state.query_validator = None
        self.state.ingest_service = None
        self.state.event_query_service = None
        self.state.timeline_service = None
        self.state.correlation_service = None
        self.state.raw_log_service = None
        self.state.aggregation_service = None
        self.state.started = False

    async def is_healthy(self) -> bool:
        if not self.state.started or self.state.store is None:
            return False
        return await self.state.store.ping()

    async def aggregate_agent_events(self, payload: object) -> dict[str, object]:
        agg_service = self.state.aggregation_service
        query_validator = self.state.query_validator
        if agg_service is None or query_validator is None:
            raise _service_not_started()
        params = query_validator.validate_aggregate_query(payload)
        result = await cast(Any, agg_service).aggregate_agent_events(params)
        return asdict(result)


def build_app(service: AgentLogAnalysisService) -> web.Application:
    """Create the aiohttp application with routes."""
    app = web.Application()
    app[SERVICE_APP_KEY] = service
    handlers_module = import_module("core.agent_log_analysis.http_handlers")
    handlers = handlers_module.AgentLogAnalysisHttpHandlers(runtime=service)
    app.router.add_get("/healthz", handlers.healthz)
    app.router.add_post("/api/v1/events/ingest", handlers.ingest_event)
    app.router.add_post("/api/v1/events/ingest-batch", handlers.ingest_batch)
    app.router.add_get("/api/v1/events/{event_id}", handlers.get_event)
    return app


def _service_not_started() -> RuntimeError:
    return RuntimeError("service is not started")


async def _setup_runner(service: AgentLogAnalysisService) -> web.AppRunner:
    app = build_app(service)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=service.config.host, port=service.config.port)
    await site.start()
    logger.info(
        "Agent log analysis listening on %s:%s",
        service.config.host,
        service.config.port,
    )
    return runner


async def _shutdown(runner: web.AppRunner, service: AgentLogAnalysisService) -> None:
    await runner.cleanup()
    await service.stop()


async def run_service() -> None:
    """Run the agent log analysis service."""

    service = AgentLogAnalysisService()
    await service.start()
    runner = await _setup_runner(service)
    try:
        await asyncio.Event().wait()
    except BaseException:
        return
    finally:
        await _shutdown(runner, service)
