from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Protocol

from core.scheduler_cron.scheduler_engine_support import (  # noqa: WPS235
    FAILED,
    RUNNING,
    SUCCESS,
    build_scheduler,
    coerce_int,
    duration_ms,
    job_args,
    job_options,
    trigger_for,
)

logger = logging.getLogger(__name__)
SYNC_INTERVAL_SECONDS = 60

_JobRow = dict[str, object]
_ExecutorCallback = Callable[
    [str, _JobRow],
    Coroutine[object, object, _JobRow],
]


class _SchedulerStoreProtocol(Protocol):
    async def list_jobs(self, enabled: bool | None = None) -> list[_JobRow]: ...  # noqa: WPS221

    async def create_run(self, job_id: str, status: str) -> str: ...

    async def complete_run(
        self,
        run_id: str,
        status: str,
        *,
        result: _JobRow | None = None,
        error_message: str | None = None,
        duration_ms: int | None = None,
    ) -> bool: ...

    async def get_job_by_id(self, job_id: str) -> _JobRow | None: ...

    async def update_job(self, name: str, **changes: object) -> bool: ...

    async def delete_job(self, name: str) -> bool: ...


class _ScheduledJobProtocol(Protocol):
    id: str


class _ApschedulerProtocol(Protocol):
    def start(self) -> None: ...

    def shutdown(self, wait: bool = True) -> None: ...

    def get_jobs(self) -> list[_ScheduledJobProtocol]: ...

    def add_job(self, **kwargs: object) -> object: ...

    def remove_job(self, job_id: str) -> None: ...

    def pause_job(self, job_id: str) -> None: ...

    def resume_job(self, job_id: str) -> None: ...


class _RunContext:
    __slots__ = ("run_id", "job_id", "started_at", "auto_delete")

    def __init__(self, run_id: str, job_id: str, started_at: datetime, auto_delete: bool) -> None:
        self.run_id = run_id
        self.job_id = job_id
        self.started_at = started_at
        self.auto_delete = auto_delete


class SchedulerEngine:  # noqa: WPS214 -- scheduler API requires start/stop/add/remove/pause/resume + __init__
    def __init__(
        self,
        store: _SchedulerStoreProtocol,
        _database_url: str,
        executor_callback: _ExecutorCallback,
    ) -> None:
        self._store = store
        self._executor_callback = executor_callback
        self._scheduler: _ApschedulerProtocol | None = None
        self._running_jobs: dict[str, str] = {}
        self._sync_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        scheduler = build_scheduler()
        self._scheduler = scheduler
        scheduler.start()
        self._sync_task = asyncio.create_task(_sync_loop(self))
        await _sync_jobs_from_db(self._store, self._scheduler)

    async def stop(self) -> None:
        task = self._sync_task
        if task is not None:
            self._sync_task = None
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass  # noqa: WPS420
        scheduler = self._scheduler
        if scheduler is None:
            return
        scheduler.shutdown(wait=True)
        self._scheduler = None

    async def add_job(self, job: _JobRow) -> None:
        _add_job_to_scheduler(self._scheduler, self._job_wrapper, job)

    async def remove_job(self, job_id: str) -> bool:
        return _call_scheduler(self._scheduler, lambda sched: sched.remove_job(job_id))

    async def pause_job(self, job_id: str) -> bool:
        return _call_scheduler(self._scheduler, lambda sched: sched.pause_job(job_id))

    async def resume_job(self, job_id: str) -> bool:
        return _call_scheduler(self._scheduler, lambda sched: sched.resume_job(job_id))

    async def _job_wrapper(
        self,
        job_id: str,
        action_type: str,
        action_payload: _JobRow,
        auto_delete: bool,
    ) -> None:
        ctx = _RunContext(
            run_id=await self._store.create_run(job_id, status=RUNNING),
            job_id=job_id,
            started_at=datetime.now(UTC),
            auto_delete=auto_delete,
        )
        self._running_jobs[job_id] = ctx.run_id
        try:
            await _run_and_complete(self, ctx, action_type, action_payload)
        except Exception as exc:
            await _complete_failure(self._store, ctx, exc)
        finally:
            self._running_jobs.pop(job_id, None)


async def _sync_loop(engine: SchedulerEngine) -> None:
    while True:
        try:
            await asyncio.sleep(SYNC_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            break
        try:
            await _sync_jobs_from_db(engine._store, engine._scheduler)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("Sync loop error: %s", exc)


async def _sync_jobs_from_db(
    store: _SchedulerStoreProtocol,
    scheduler: _ApschedulerProtocol | None,
) -> None:
    if scheduler is None:
        return
    existing = {str(job.id) for job in scheduler.get_jobs()}
    jobs = await store.list_jobs(enabled=True)
    for job in jobs:
        if str(job["id"]) not in existing:
            _add_job_raw(scheduler, job)


def _add_job_raw(scheduler: _ApschedulerProtocol, job: _JobRow) -> None:
    job_type = str(job["job_type"])
    schedule = str(job["schedule"])
    trigger = trigger_for(job_type=job_type, schedule=schedule)
    scheduler.add_job(
        trigger=trigger,
        id=str(job["id"]),
        name=str(job["name"]),
        args=job_args(job),
        **job_options(job),
    )


def _add_job_to_scheduler(
    scheduler: _ApschedulerProtocol | None,
    func: object,
    job: _JobRow,
) -> None:
    if scheduler is None:
        return
    job_type = str(job["job_type"])
    schedule = str(job["schedule"])
    trigger = trigger_for(job_type=job_type, schedule=schedule)  # noqa: WPS221
    scheduler.add_job(
        func=func,
        trigger=trigger,
        id=str(job["id"]),
        name=str(job["name"]),
        args=job_args(job),
        **job_options(job),
    )


async def _run_and_complete(
    engine: SchedulerEngine,
    ctx: _RunContext,
    action_type: str,
    action_payload: _JobRow,
) -> None:
    result = await engine._executor_callback(action_type, action_payload)
    await _complete_success(engine, ctx, result)


async def _complete_success(
    engine: SchedulerEngine,
    ctx: _RunContext,
    result: _JobRow,
) -> None:
    store = engine._store
    await store.complete_run(
        ctx.run_id,
        status=SUCCESS,
        result=result,
        duration_ms=duration_ms(ctx.started_at),
    )
    job = await store.get_job_by_id(ctx.job_id)
    if job is None:
        return
    await store.update_job(
        str(job["name"]),
        last_run_at=ctx.started_at,
        run_count=coerce_int(job.get("run_count")) + 1,
    )
    if ctx.auto_delete:
        await engine.remove_job(ctx.job_id)
        await store.delete_job(str(job["name"]))


async def _complete_failure(
    store: _SchedulerStoreProtocol,
    ctx: _RunContext,
    error: Exception,
) -> None:
    await store.complete_run(
        ctx.run_id,
        status=FAILED,
        error_message=str(error)[:1024],
        duration_ms=duration_ms(ctx.started_at),
    )
    job = await store.get_job_by_id(ctx.job_id)
    if job is None:
        return
    await store.update_job(
        str(job["name"]),
        failure_count=coerce_int(job.get("failure_count")) + 1,
    )
    logger.error("Job %s failed: %s", ctx.job_id, error)


def _call_scheduler(
    scheduler: _ApschedulerProtocol | None,
    operation: Callable[[_ApschedulerProtocol], None],
) -> bool:
    if scheduler is None:
        return False
    try:
        operation(scheduler)
    except Exception:
        return False
    return True
