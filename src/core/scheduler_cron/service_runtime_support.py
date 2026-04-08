from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, TypeVar

from aiohttp import web

from core.scheduler_cron.executor import JobExecutor
from core.scheduler_cron.scheduler_engine import SchedulerEngine
from core.scheduler_cron.store import SchedulerCronStore

DEFAULT_EVENTS_ENGINE_URL = "http://events-engine:8789"
SERVICE_UNAVAILABLE = 503


class _StartableService(Protocol):
    async def start(self) -> None: ...


TService = TypeVar("TService", bound=_StartableService)


async def stop_optional(component: SchedulerEngine | JobExecutor | None) -> None:
    if component is not None:
        await component.stop()


async def start_executor(events_engine_url: str) -> JobExecutor:
    executor = JobExecutor(events_engine_url)
    await executor.start()
    return executor


async def start_engine(
    store: SchedulerCronStore,
    database_url: str,
    executor: JobExecutor,
) -> SchedulerEngine:
    engine = SchedulerEngine(store, database_url, executor.execute)
    await engine.start()
    return engine


async def start_web_runner(
    service: TService,
    app_factory: Callable[[TService], web.Application],
    *,
    host: str,
    port: int,
) -> web.AppRunner:
    await service.start()
    runner = web.AppRunner(app_factory(service))
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
    return runner
