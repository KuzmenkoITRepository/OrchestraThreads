from __future__ import annotations

from typing import Protocol

from aiohttp import web

from core.task_registry.config import TaskRegistryConfig

HTTP_UNAVAILABLE_STATUS = 503


class _HealthyService(Protocol):
    config: TaskRegistryConfig

    async def is_healthy(self) -> bool: ...

    async def stop(self) -> None: ...


SERVICE_KEY = web.AppKey("task_registry_service", _HealthyService)


async def setup_app(service: _HealthyService) -> web.AppRunner:
    app = web.Application()
    app[SERVICE_KEY] = service
    app.router.add_get("/healthz", _healthz)
    runner = web.AppRunner(app)
    await runner.setup()
    return runner


async def start_site(runner: web.AppRunner, config: TaskRegistryConfig) -> None:
    site = web.TCPSite(runner, host=config.host, port=config.port)
    await site.start()


async def stop_service(service: _HealthyService, runner: web.AppRunner) -> None:
    await runner.cleanup()
    await service.stop()


async def _healthz(request: web.Request) -> web.Response:
    service = request.app[SERVICE_KEY]
    if not await service.is_healthy():
        return web.json_response({"status": "error"}, status=HTTP_UNAVAILABLE_STATUS)
    return web.json_response({"status": "ok"})
