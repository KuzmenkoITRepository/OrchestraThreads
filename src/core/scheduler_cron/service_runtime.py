from __future__ import annotations

import asyncio
import logging
import os

from aiohttp import web

from core.scheduler_cron.bootstrap import bootstrap_jobs
from core.scheduler_cron.config import SchedulerCronConfig, load_config
from core.scheduler_cron.executor import JobExecutor
from core.scheduler_cron.scheduler_engine import SchedulerEngine
from core.scheduler_cron.service_runtime_support import (
    DEFAULT_EVENTS_ENGINE_URL,
    SERVICE_UNAVAILABLE,
    StartedRuntime,
    start_runtime,
    stop_runtime,
)
from core.scheduler_cron.store import SchedulerCronStore

logger = logging.getLogger(__name__)


class SchedulerCronService:
    def __init__(self, config: SchedulerCronConfig | None = None) -> None:
        self.config = load_config() if config is None else config
        self.store = SchedulerCronStore(self.config.database_url, schema_name=self.config.db_schema)
        self._engine: SchedulerEngine | None = None
        self._executor: JobExecutor | None = None
        self._runtime: StartedRuntime | None = None
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        await self.store.start()
        runtime = await start_runtime(
            store=self.store,
            database_url=self.config.database_url,
            events_engine_url=_events_engine_url(),
            executor_type=JobExecutor,
            engine_type=SchedulerEngine,
        )
        self._set_runtime(runtime)
        await bootstrap_jobs(self.store, runtime.engine)
        self._started = True

    async def stop(self) -> None:
        if not self._started:
            return
        await stop_runtime(self._runtime)
        self._clear_runtime()
        await self.store.close()
        self._started = False

    async def is_healthy(self) -> bool:
        return bool(await self.store.ping())

    async def handle_healthz(self, _: web.Request) -> web.Response:
        if not await self.is_healthy():
            return web.json_response({"status": "error"}, status=SERVICE_UNAVAILABLE)
        return web.json_response({"status": "ok"})

    def _set_runtime(self, runtime: StartedRuntime) -> None:
        self._runtime = runtime
        self._executor = runtime.executor
        self._engine = runtime.engine

    def _clear_runtime(self) -> None:
        self._runtime = None
        self._engine = None
        self._executor = None


def build_app(service: SchedulerCronService) -> web.Application:
    app = web.Application()
    app["service"] = service
    app.router.add_get("/healthz", service.handle_healthz)
    return app


async def _start_web_service(service: SchedulerCronService) -> web.AppRunner:
    await service.start()
    runner = web.AppRunner(build_app(service))
    await runner.setup()
    site = web.TCPSite(runner, host=service.config.host, port=service.config.port)
    await site.start()
    return runner


async def _stop_web_service(service: SchedulerCronService, runner: web.AppRunner) -> None:
    await runner.cleanup()
    await service.stop()


async def run_service() -> None:
    service = SchedulerCronService()
    runner = await _start_web_service(service)
    logger.info("scheduler_cron listening on %s:%s", service.config.host, service.config.port)
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        raise
    finally:
        await _stop_web_service(service, runner)


def _events_engine_url() -> str:
    return os.getenv("EVENTS_ENGINE_URL", DEFAULT_EVENTS_ENGINE_URL)
