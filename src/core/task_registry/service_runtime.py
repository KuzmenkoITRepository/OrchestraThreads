"""HTTP runtime for the task registry service."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from aiohttp import web

from core.task_registry.config import TaskRegistryConfig, load_config

logger = logging.getLogger(__name__)


@dataclass
class TaskRegistryStore:
    """Placeholder task registry store."""

    database_url: str
    running: bool = False

    async def start(self) -> None:
        self.running = True

    async def close(self) -> None:
        self.running = False

    async def ping(self) -> bool:
        return self.running


class TaskRegistryService:
    """Task registry HTTP service."""

    def __init__(self, config: TaskRegistryConfig | None = None) -> None:
        self.config = config or load_config()
        self.store = TaskRegistryStore(self.config.database_url)
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        await self.store.start()
        self._started = True

    async def stop(self) -> None:
        if not self._started:
            return
        await self.store.close()
        self._started = False

    async def is_healthy(self) -> bool:
        return await self.store.ping()


async def _setup_app(service: TaskRegistryService) -> tuple[web.Application, web.AppRunner]:
    app = web.Application()
    app["service"] = service
    app.router.add_get("/healthz", _healthz)
    runner = web.AppRunner(app)
    await runner.setup()
    return app, runner


async def _shutdown_service(service: TaskRegistryService, runner: web.AppRunner) -> None:
    await runner.cleanup()
    await service.stop()


async def _healthz(request: web.Request) -> web.Response:
    service = request.app["service"]
    if not isinstance(service, TaskRegistryService):
        return web.json_response({"status": "error"}, status=503)
    if not await service.is_healthy():
        return web.json_response({"status": "error"}, status=503)
    return web.json_response({"status": "ok"})


async def run_service() -> None:
    service = TaskRegistryService()
    await service.start()
    _, runner = await _setup_app(service)
    site = web.TCPSite(runner, host=service.config.host, port=service.config.port)
    await site.start()
    logger.info("Task registry listening on %s:%s", service.config.host, service.config.port)
    try:
        await asyncio.Event().wait()
    except BaseException:
        return
    finally:
        await _shutdown_service(service, runner)
