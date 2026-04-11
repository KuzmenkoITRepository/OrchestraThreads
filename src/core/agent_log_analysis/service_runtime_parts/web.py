"""Aiohttp app and runner helpers for the agent log analysis runtime."""

from __future__ import annotations

import logging
from importlib import import_module
from typing import TYPE_CHECKING, Any

from aiohttp import web

if TYPE_CHECKING:
    from core.agent_log_analysis.service_runtime import AgentLogAnalysisService

logger = logging.getLogger(__name__)


def build_service_app(
    service: AgentLogAnalysisService,
    app_key: web.AppKey[AgentLogAnalysisService],
) -> web.Application:
    """Create the aiohttp application and register stable routes."""
    app = web.Application()
    app[app_key] = service
    handlers = _build_handlers(service)
    _register_routes(app, handlers)
    return app


async def setup_runner(
    service: AgentLogAnalysisService,
    app: web.Application,
) -> web.AppRunner:
    """Prepare and start the public TCP site for the service."""
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


async def shutdown_runner(
    runner: web.AppRunner,
    service: AgentLogAnalysisService,
) -> None:
    """Stop the aiohttp runner and then stop runtime dependencies."""
    await runner.cleanup()
    await service.stop()


def _build_handlers(service: AgentLogAnalysisService) -> Any:
    handlers_module = import_module("core.agent_log_analysis.http_handlers")
    return handlers_module.AgentLogAnalysisHttpHandlers(runtime=service)


def _register_routes(app: web.Application, handlers: Any) -> None:
    app.router.add_get("/healthz", handlers.healthz)
    app.router.add_post("/api/v1/events/ingest", handlers.ingest_event)
    app.router.add_post("/api/v1/events/ingest-batch", handlers.ingest_batch)
    app.router.add_get("/api/v1/events/{event_id}", handlers.get_event)
