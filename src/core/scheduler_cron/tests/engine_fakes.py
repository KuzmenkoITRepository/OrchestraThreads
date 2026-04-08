"""Fake implementations for SchedulerEngine tests."""

from __future__ import annotations

from typing import Any

from core.scheduler_cron.scheduler_engine_types import SchedulerProtocol


class FakeScheduledJob:
    """Minimal scheduled job stub."""

    def __init__(self, job_id: str) -> None:
        self.id = job_id


class FakeScheduler(SchedulerProtocol):  # noqa: WPS214 - scheduler stub mirrors real API surface
    """Minimal scheduler stub that records calls."""

    def __init__(self) -> None:
        self.started = False
        self.shutdown_calls: list[bool] = []
        self.add_job_calls: list[dict[str, object]] = []
        self.remove_job_calls: list[str] = []
        self.pause_job_calls: list[str] = []
        self.resume_job_calls: list[str] = []
        self._jobs: dict[str, FakeScheduledJob] = {}

    def seed_job_ids(self, job_ids: list[str]) -> None:
        for job_id in job_ids:
            self._jobs[job_id] = FakeScheduledJob(job_id)

    def start(self) -> None:
        self.started = True

    def shutdown(self, wait: bool = True) -> None:
        self.shutdown_calls.append(wait)

    def get_jobs(self) -> list[Any]:  # noqa: WPS615 - mirrors APScheduler API required by SchedulerProtocol
        return list(self._jobs.values())

    def add_job(self, **kwargs: object) -> object:
        self.add_job_calls.append(kwargs)
        job_id = str(kwargs["id"])
        self._jobs[job_id] = FakeScheduledJob(job_id)
        return FakeScheduledJob(job_id)

    def remove_job(self, job_id: str) -> None:
        self.remove_job_calls.append(job_id)
        self._jobs.pop(job_id, None)

    def pause_job(self, job_id: str) -> None:
        self.pause_job_calls.append(job_id)

    def resume_job(self, job_id: str) -> None:
        self.resume_job_calls.append(job_id)


ExecutorCall = tuple[str, dict[str, object]]


class FakeExecutor:
    """Executor stub that records calls and can raise."""

    def __init__(
        self,
        response: dict[str, object] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response or {"ok": True}
        self.error = error
        self.calls: list[ExecutorCall] = []

    async def __call__(
        self,
        action_type: str,
        action_payload: dict[str, object],
    ) -> dict[str, object]:
        self.calls.append((action_type, action_payload))
        if self.error is not None:
            raise self.error
        return self.response
