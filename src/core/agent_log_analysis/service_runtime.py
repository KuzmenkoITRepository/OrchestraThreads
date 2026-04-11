"""HTTP runtime for the agent log analysis service."""

from __future__ import annotations

import asyncio

from aiohttp import web

from core.agent_log_analysis import config as log_config
from core.agent_log_analysis import service_state
from core.agent_log_analysis.service_runtime_parts.dependencies import (
    start_service_state,
    stop_service_state,
)
from core.agent_log_analysis.service_runtime_parts.operations import (
    IngestOperations,
    QueryOperations,
)
from core.agent_log_analysis.service_runtime_parts.web import (
    build_service_app,
    setup_runner,
    shutdown_runner,
)

SERVICE_APP_KEY: web.AppKey[AgentLogAnalysisService] = web.AppKey("AgentLogAnalysisService")


class AgentLogAnalysisService(IngestOperations, QueryOperations):
    """Agent log analysis HTTP service."""

    def __init__(self, config: log_config.AgentLogAnalysisConfig | None = None) -> None:
        self.config = config or log_config.load_config()
        self.state = service_state.ServiceState(config=self.config)

    async def start(self) -> None:
        if self.state.started:
            return
        await start_service_state(self.state)

    async def stop(self) -> None:
        if not self.state.started:
            return
        await stop_service_state(self.state)

    async def is_healthy(self) -> bool:
        if not self.state.started or self.state.store is None:
            return False
        return await self.state.store.ping()


def build_app(service: AgentLogAnalysisService) -> web.Application:
    """Create the aiohttp application with routes."""
    return build_service_app(service, SERVICE_APP_KEY)


async def run_service() -> None:
    """Run the agent log analysis service."""

    service = AgentLogAnalysisService()
    await service.start()
    runner = await setup_runner(service, build_app(service))
    try:
        await asyncio.Event().wait()
    except BaseException:
        return
    finally:
        await shutdown_runner(runner, service)
