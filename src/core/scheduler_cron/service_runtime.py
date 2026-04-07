from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from importlib import import_module
from typing import Any, Protocol, cast

from aiohttp import web

_config_module = cast(Any, import_module("core.scheduler_cron.config"))
_bootstrap_module = cast(Any, import_module("core.scheduler_cron.bootstrap"))
_executor_module = cast(Any, import_module("core.scheduler_cron.executor"))
_engine_module = cast(Any, import_module("core.scheduler_cron.scheduler_engine"))
_store_module = cast(Any, import_module("core.scheduler_cron.store"))

SchedulerCronConfig = cast(type, _config_module.SchedulerCronConfig)
load_config = cast(Any, _config_module.load_config)
bootstrap_jobs = cast(Any, _bootstrap_module.bootstrap_jobs)
JobExecutor = cast(type, _executor_module.JobExecutor)
SchedulerEngine = cast(type, _engine_module.SchedulerEngine)
SchedulerCronStore = cast(type, _store_module.SchedulerCronStore)

logger = logging.getLogger(__name__)
DEFAULT_EVENTS_ENGINE_URL = "http://events-engine:8789"


class _StoreProtocol(Protocol):
    async def start(self) -> None: ...

    async def close(self) -> None: ...

    async def ping(self) -> bool: ...

    async def get_job_by_name(self, name: str) -> dict[str, object] | None: ...

    async def get_job_by_id(self, job_id: str) -> dict[str, object] | None: ...

    async def create_job(self, **kwargs: object) -> str: ...

    async def update_job(self, name: str, **changes: object) -> bool: ...


class _ExecutorProtocol(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def execute(
        self, action_type: str, action_payload: dict[str, object]
    ) -> dict[str, object]: ...


class _EngineProtocol(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def add_job(self, job: dict[str, object]) -> None: ...


class _ConfigProtocol(Protocol):
    host: str
    port: int
    database_url: str
    db_schema: str


@dataclass(frozen=True)
class _ServiceDependencies:
    store: _StoreProtocol
    executor: _ExecutorProtocol
    engine: _EngineProtocol


class SchedulerCronService:
    def __init__(self, config: _ConfigProtocol | None = None) -> None:
        self.config: _ConfigProtocol = (
            cast(_ConfigProtocol, load_config()) if config is None else config
        )
        self.store: _StoreProtocol = cast(
            _StoreProtocol,
            SchedulerCronStore(self.config.database_url, schema_name=self.config.db_schema),
        )
        self._engine: _EngineProtocol | None = None
        self._executor: _ExecutorProtocol | None = None
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        dependencies = await self._build_dependencies()
        self._executor = dependencies.executor
        self._engine = dependencies.engine
        await bootstrap_jobs(dependencies.store, dependencies.engine)
        self._started = True

    async def _build_dependencies(self) -> _ServiceDependencies:
        await self.store.start()
        executor = cast(_ExecutorProtocol, JobExecutor(_events_engine_url()))
        await executor.start()
        engine = cast(
            _EngineProtocol,
            SchedulerEngine(self.store, self.config.database_url, executor.execute),
        )
        await engine.start()
        return _ServiceDependencies(store=self.store, executor=executor, engine=engine)

    async def stop(self) -> None:
        if not self._started:
            return
        await _stop_optional(self._engine)
        await _stop_optional(self._executor)
        self._engine = None
        self._executor = None
        await self.store.close()
        self._started = False

    async def is_healthy(self) -> bool:
        return await self.store.ping()

    async def handle_healthz(self, _: web.Request) -> web.Response:
        if not await self.is_healthy():
            return web.json_response({"status": "error"}, status=503)
        return web.json_response({"status": "ok"})


def build_app(service: SchedulerCronService) -> web.Application:
    app = web.Application()
    app["service"] = service
    app.router.add_get("/healthz", service.handle_healthz)
    return app


async def run_service() -> None:
    service = SchedulerCronService()
    await service.start()
    runner = web.AppRunner(build_app(service))
    await runner.setup()
    site = web.TCPSite(runner, host=service.config.host, port=service.config.port)
    await site.start()
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


async def _stop_optional(component: _EngineProtocol | _ExecutorProtocol | None) -> None:
    if component is not None:
        await component.stop()
