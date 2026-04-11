from __future__ import annotations

from dataclasses import dataclass

from core.scheduler_cron.executor import JobExecutor
from core.scheduler_cron.scheduler_engine import SchedulerEngine
from core.scheduler_cron.store import SchedulerCronStore

DEFAULT_EVENTS_ENGINE_URL = "http://events-engine:8789"
SERVICE_UNAVAILABLE = 503


@dataclass(frozen=True)
class StartedRuntime:
    executor: JobExecutor
    engine: SchedulerEngine


async def start_runtime(
    *,
    store: SchedulerCronStore,
    database_url: str,
    events_engine_url: str,
    executor_type: type[JobExecutor],
    engine_type: type[SchedulerEngine],
) -> StartedRuntime:
    executor = await start_executor_with(executor_type, events_engine_url)
    engine = await start_engine_with(engine_type, store, database_url, executor)
    return StartedRuntime(executor=executor, engine=engine)


async def stop_runtime(runtime: StartedRuntime | None) -> None:
    if runtime is None:
        return
    await runtime.engine.stop()
    await runtime.executor.stop()


async def start_executor_with(
    executor_type: type[JobExecutor],
    events_engine_url: str,
) -> JobExecutor:
    executor = executor_type(events_engine_url)
    await executor.start()
    return executor


async def start_engine_with(
    engine_type: type[SchedulerEngine],
    store: SchedulerCronStore,
    database_url: str,
    executor: JobExecutor,
) -> SchedulerEngine:
    engine = engine_type(store, database_url, executor.execute)
    await engine.start()
    return engine
