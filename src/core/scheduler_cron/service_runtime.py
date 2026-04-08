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
    start_engine,
    start_executor,
    start_web_runner,
    stop_optional,
)
from core.scheduler_cron.store import SchedulerCronStore

logger = logging.getLogger(__name__)


class SchedulerCronService:
    def __init__(self, config: SchedulerCronConfig | None = None) -> None:
        self.config = load_config() if config is None else config
        self.store = SchedulerCronStore(self.config.database_url, schema_name=self.config.db_schema)
        self._engine: SchedulerEngine | None = None
        self._executor: JobExecutor | None = None
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        await self.store.start()
        self._executor = await start_executor(_events_engine_url())
        self._engine = await start_engine(self.store, self.config.database_url, self._executor)
        await bootstrap_jobs(self.store, self._engine)
        self._started = True

    async def stop(self) -> None:
        if not self._started:
            return
        await stop_optional(self._engine)
        await stop_optional(self._executor)
        self._engine = None
        self._executor = None
        await self.store.close()
        self._started = False

    async def is_healthy(self) -> bool:
        return bool(await self.store.ping())

    async def handle_healthz(self, _: web.Request) -> web.Response:
        if not await self.is_healthy():
            return web.json_response({"status": "error"}, status=SERVICE_UNAVAILABLE)
        return web.json_response({"status": "ok"})


def build_app(service: SchedulerCronService) -> web.Application:
    app = web.Application()
    app["service"] = service
    app.router.add_get("/healthz", service.handle_healthz)
    return app


async def run_service() -> None:
    service = SchedulerCronService()
    runner = await start_web_runner(
        service,
        build_app,
        host=service.config.host,
        port=service.config.port,
    )
    logger.info("scheduler_cron listening on %s:%s", service.config.host, service.config.port)
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        raise
    finally:
        await runner.cleanup()
        await service.stop()


def _events_engine_url() -> str:
    return os.getenv("EVENTS_ENGINE_URL", DEFAULT_EVENTS_ENGINE_URL)
