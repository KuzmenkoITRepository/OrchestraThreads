from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime

from core.scheduler_cron import scheduler_engine_support
from core.scheduler_cron.scheduler_engine_types import (
    ExecutorCallbackProtocol,
    JobRunner,
    RemoveJobCallback,
    SchedulerProtocol,
    SchedulerStoreProtocol,
)

build_scheduler = scheduler_engine_support.build_scheduler
trigger_for = scheduler_engine_support.trigger_for
job_args = scheduler_engine_support.job_args
job_options = scheduler_engine_support.job_options

logger = logging.getLogger(__name__)
SYNC_INTERVAL_SECONDS = 60
NAME_FIELD = "name"


class _SchedulerWorker:
    def __init__(
        self,
        store: SchedulerStoreProtocol,
        executor_callback: ExecutorCallbackProtocol,
        running_jobs: dict[str, str],
        remove_job: RemoveJobCallback,
    ) -> None:
        self._store = store
        self._executor_callback = executor_callback
        self._running_jobs = running_jobs
        self._remove_job = remove_job

    async def sync_loop(
        self,
        scheduler: SchedulerProtocol,
        sync_interval_seconds: int,
        job_runner: JobRunner,
    ) -> None:
        while True:
            try:
                await asyncio.sleep(sync_interval_seconds)
            except asyncio.CancelledError:
                break
            try:
                await self.sync_jobs_from_db(scheduler, job_runner)
            except Exception as error:
                logger.error("Sync loop error: %s", error)

    async def sync_jobs_from_db(
        self,
        scheduler: SchedulerProtocol,
        job_runner: JobRunner,
    ) -> None:
        existing = {str(job.id) for job in scheduler.get_jobs()}
        jobs = await self._store.list_jobs(enabled=True)
        missing = [job for job in jobs if str(job["id"]) not in existing]
        await asyncio.gather(
            *(self.add_job_to_scheduler(scheduler, job, job_runner) for job in missing)
        )

    async def add_job_to_scheduler(
        self,
        scheduler: SchedulerProtocol,
        job: dict[str, object],
        job_runner: JobRunner,
    ) -> None:
        scheduler.add_job(
            func=job_runner,
            trigger=trigger_for(
                job_type=str(job["job_type"]),
                schedule=str(job["schedule"]),
            ),
            id=str(job["id"]),
            name=str(job[NAME_FIELD]),
            args=job_args(job),
            **job_options(job),
        )

    async def run_job(
        self,
        job_id: str,
        action_type: str,
        action_payload: dict[str, object],
        auto_delete: bool,
    ) -> None:
        run_id = await self._store.create_run(job_id, status=scheduler_engine_support.RUNNING)
        self._running_jobs[job_id] = run_id
        started_at = datetime.now(UTC)
        try:
            run_result = await self._executor_callback(action_type, action_payload)
        except Exception as error:
            await self._complete_failure(run_id, job_id, started_at, error)
        else:
            await self._complete_success(run_id, job_id, started_at, run_result, auto_delete)
        finally:
            self._running_jobs.pop(job_id, None)

    async def _complete_success(
        self,
        run_id: str,
        job_id: str,
        started_at: datetime,
        run_result: dict[str, object],
        auto_delete: bool,
    ) -> None:
        await self._store.complete_run(
            run_id,
            status=scheduler_engine_support.SUCCESS,
            result=run_result,
            duration_ms=scheduler_engine_support.duration_ms(started_at),
        )
        job = await self._store.get_job_by_id(job_id)
        if job is None:
            return
        await self._store.update_job(
            str(job[NAME_FIELD]),
            last_run_at=started_at,
            run_count=scheduler_engine_support.coerce_int(job.get("run_count")) + 1,
        )
        if not auto_delete:
            return
        await self._remove_job(job_id)
        await self._store.delete_job(str(job[NAME_FIELD]))

    async def _complete_failure(
        self,
        run_id: str,
        job_id: str,
        started_at: datetime,
        error: Exception,
    ) -> None:
        await self._store.complete_run(
            run_id,
            status=scheduler_engine_support.FAILED,
            error_message=str(error)[:1024],
            duration_ms=scheduler_engine_support.duration_ms(started_at),
        )
        job = await self._store.get_job_by_id(job_id)
        if job is None:
            return
        await self._store.update_job(
            str(job[NAME_FIELD]),
            failure_count=scheduler_engine_support.coerce_int(job.get("failure_count")) + 1,
        )
        logger.error("Job %s failed: %s", job_id, error)


class SchedulerEngine:
    def __init__(
        self,
        store: SchedulerStoreProtocol,
        _database_url: str,
        executor_callback: ExecutorCallbackProtocol,
    ) -> None:
        self._store = store
        self._scheduler: SchedulerProtocol | None = None
        self._running_jobs: dict[str, str] = {}
        self._sync_task: asyncio.Task[None] | None = None
        self._worker = _SchedulerWorker(
            store=store,
            executor_callback=executor_callback,
            running_jobs=self._running_jobs,
            remove_job=self.remove_job,
        )
        self._job_wrapper = _compat_job_wrapper.__get__(self, type(self))
        self._sync_jobs_from_db = _compat_sync_jobs_from_db.__get__(self, type(self))

    async def start(self) -> None:
        scheduler = build_scheduler()
        self._scheduler = scheduler
        scheduler.start()
        self._sync_task = asyncio.create_task(
            self._worker.sync_loop(
                scheduler,
                sync_interval_seconds=SYNC_INTERVAL_SECONDS,
                job_runner=self._job_wrapper,
            )
        )
        await self._sync_jobs_from_db()

    async def stop(self) -> None:
        if self._sync_task is not None:
            self._sync_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._sync_task
            self._sync_task = None
        scheduler = self._scheduler
        if scheduler is None:
            return
        scheduler.shutdown(wait=True)
        self._scheduler = None

    async def add_job(self, job: dict[str, object]) -> None:
        scheduler = self._scheduler
        if scheduler is None:
            return
        await self._worker.add_job_to_scheduler(scheduler, job, self._job_wrapper)

    async def remove_job(self, job_id: str) -> bool:
        return _call_scheduler(self._scheduler, lambda scheduler: scheduler.remove_job(job_id))

    async def pause_job(self, job_id: str) -> bool:
        return _call_scheduler(self._scheduler, lambda scheduler: scheduler.pause_job(job_id))

    async def resume_job(self, job_id: str) -> bool:
        return _call_scheduler(self._scheduler, lambda scheduler: scheduler.resume_job(job_id))


def _call_scheduler(
    scheduler: SchedulerProtocol | None,
    operation: Callable[[SchedulerProtocol], None],
) -> bool:
    if scheduler is None:
        return False
    try:
        operation(scheduler)
    except Exception:
        return False
    return True


async def _compat_job_wrapper(
    engine: SchedulerEngine,
    job_id: str,
    action_type: str,
    action_payload: dict[str, object],
    auto_delete: bool,
) -> None:
    await engine._worker.run_job(job_id, action_type, action_payload, auto_delete)


async def _compat_sync_jobs_from_db(engine: SchedulerEngine) -> None:
    scheduler = engine._scheduler
    if scheduler is None:
        return
    await engine._worker.sync_jobs_from_db(scheduler, engine._job_wrapper)
