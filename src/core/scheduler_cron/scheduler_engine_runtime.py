from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from core.scheduler_cron.scheduler_engine_support import (
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
STOP_WAIT_TIMEOUT_SECONDS = 5.0
STOP_WAIT_POLL_SECONDS = 0.05
ZERO_SECONDS = 0


class _SchedulerStoreProtocol(Protocol):
    async def list_jobs(self, enabled: bool | None = None) -> list[dict[str, object]]: ...

    async def create_run(self, job_id: str, status: str) -> str: ...

    async def complete_run(
        self,
        run_id: str,
        status: str,
        *,
        result: dict[str, object] | None = None,
        error_message: str | None = None,
        duration_ms: int | None = None,
    ) -> bool: ...

    async def get_job_by_id(self, job_id: str) -> dict[str, object] | None: ...

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


@dataclass(frozen=True)
class _SuccessPayload:
    job_id: str
    started_at: datetime
    result: dict[str, object]


class SchedulerEngine:
    def __init__(
        self,
        store: _SchedulerStoreProtocol,
        _database_url: str,
        executor_callback: Callable[
            [str, dict[str, object]],
            Coroutine[object, object, dict[str, object]],
        ],
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
        self._sync_task = asyncio.create_task(self._sync_loop())
        await self._sync_jobs_from_db()

    async def stop(self) -> None:
        await self._stop_sync_task()
        await self._wait_running_jobs()
        scheduler = self._scheduler
        if scheduler is None:
            return
        scheduler.shutdown(wait=True)
        self._scheduler = None

    async def add_job(self, job: dict[str, object]) -> None:
        await self._add_job_to_scheduler(job)

    async def remove_job(self, job_id: str) -> bool:
        return _call_scheduler(self._scheduler, lambda scheduler: scheduler.remove_job(job_id))

    async def pause_job(self, job_id: str) -> bool:
        return _call_scheduler(self._scheduler, lambda scheduler: scheduler.pause_job(job_id))

    async def resume_job(self, job_id: str) -> bool:
        return _call_scheduler(self._scheduler, lambda scheduler: scheduler.resume_job(job_id))

    async def _stop_sync_task(self) -> None:
        if self._sync_task is None:
            return
        self._sync_task.cancel()
        try:
            await self._sync_task
        except asyncio.CancelledError:
            return
        finally:
            self._sync_task = None

    async def _wait_running_jobs(self) -> None:
        deadline = asyncio.get_running_loop().time() + STOP_WAIT_TIMEOUT_SECONDS
        while self._running_jobs and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(STOP_WAIT_POLL_SECONDS)

    async def _sync_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(SYNC_INTERVAL_SECONDS)
                await self._sync_jobs_from_db()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Sync loop error: %s", exc)

    async def _sync_jobs_from_db(self) -> None:
        scheduler = self._scheduler
        if scheduler is None:
            return
        existing = {str(job.id) for job in scheduler.get_jobs()}
        jobs = await self._store.list_jobs(enabled=True)
        missing_jobs = [job for job in jobs if str(job["id"]) not in existing]
        await asyncio.gather(*(self._add_job_to_scheduler(job) for job in missing_jobs))

    async def _add_job_to_scheduler(self, job: dict[str, object]) -> None:
        scheduler = self._scheduler
        if scheduler is None:
            return
        scheduler.add_job(
            func=self._job_wrapper,
            trigger=trigger_for(job_type=str(job["job_type"]), schedule=str(job["schedule"])),
            id=str(job["id"]),
            name=str(job["name"]),
            args=job_args(job),
            **job_options(job),
        )

    async def _job_wrapper(
        self,
        job_id: str,
        action_type: str,
        action_payload: dict[str, object],
        auto_delete: bool,
    ) -> None:
        run_id = await self._store.create_run(job_id, status=RUNNING)
        self._running_jobs[job_id] = run_id
        started_at = datetime.now(UTC)
        try:
            result = await self._executor_callback(action_type, action_payload)
            await self._complete_success(run_id, job_id, started_at, result, auto_delete)
        except Exception as exc:
            await self._complete_failure(run_id, job_id, started_at, exc)
        finally:
            self._running_jobs.pop(job_id, None)

    async def _complete_success(
        self,
        run_id: str,
        job_id: str,
        started_at: datetime,
        result: dict[str, object],
        auto_delete: bool,
    ) -> None:
        job = await self._store.get_job_by_id(job_id)
        if job is None:
            await self._mark_run_success(run_id, started_at, result)
            return
        await self._finish_successful_job(
            run_id=run_id,
            job=job,
            success=_SuccessPayload(
                job_id=job_id,
                started_at=started_at,
                result=result,
            ),
            auto_delete=auto_delete,
        )

    async def _finish_successful_job(
        self,
        *,
        run_id: str,
        job: dict[str, object],
        success: _SuccessPayload,
        auto_delete: bool,
    ) -> None:
        await self._update_job_success(job, success.started_at)
        await self._mark_run_success(run_id, success.started_at, success.result)
        if auto_delete:
            await self._delete_completed_job(success.job_id, str(job["name"]))

    async def _update_job_success(
        self,
        job: dict[str, object],
        started_at: datetime,
    ) -> None:
        await self._store.update_job(
            str(job["name"]),
            last_run_at=started_at,
            run_count=coerce_int(job.get("run_count")) + 1,
        )

    async def _mark_run_success(
        self,
        run_id: str,
        started_at: datetime,
        result: dict[str, object],
    ) -> None:
        await self._store.complete_run(
            run_id,
            status=SUCCESS,
            result=result,
            duration_ms=duration_ms(started_at),
        )

    async def _delete_completed_job(self, job_id: str, job_name: str) -> None:
        await self.remove_job(job_id)
        await self._store.delete_job(job_name)

    async def _complete_failure(
        self,
        run_id: str,
        job_id: str,
        started_at: datetime,
        error: Exception,
    ) -> None:
        await self._store.complete_run(
            run_id,
            status=FAILED,
            error_message=str(error)[:1024],
            duration_ms=duration_ms(started_at),
        )
        job = await self._store.get_job_by_id(job_id)
        if job is None:
            return
        await self._store.update_job(
            str(job["name"]),
            failure_count=coerce_int(job.get("failure_count")) + 1,
        )
        logger.error("Job %s failed: %s", job_id, error)


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
