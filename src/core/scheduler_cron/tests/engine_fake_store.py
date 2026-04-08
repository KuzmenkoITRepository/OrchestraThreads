"""Fake store implementation for SchedulerEngine tests."""

from __future__ import annotations

from typing import Unpack

from core.scheduler_cron.scheduler_engine_types import CompleteRunChanges


class FakeStore:  # noqa: WPS214 - store stub mirrors real store API surface
    """In-memory store stub for engine tests."""

    def __init__(
        self,
        jobs: list[dict[str, object]] | None = None,
    ) -> None:
        initial_jobs = jobs or []
        self.jobs_by_id: dict[str, dict[str, object]] = {
            str(job_record["id"]): dict(job_record) for job_record in initial_jobs
        }
        self.created_runs: list[dict[str, str]] = []
        self.completed_runs: list[dict[str, object]] = []
        self.list_jobs_calls: list[bool | None] = []
        self.update_calls: list[dict[str, object]] = []
        self.deleted_jobs: list[str] = []
        self._run_counter = 0

    async def list_jobs(
        self,
        enabled: bool | None = None,
    ) -> list[dict[str, object]]:
        self.list_jobs_calls.append(enabled)
        if enabled is None:
            return [dict(job_record) for job_record in self.jobs_by_id.values()]
        matched_jobs = [
            job_record
            for job_record in self.jobs_by_id.values()
            if _is_enabled(job_record) is enabled
        ]
        return [dict(job_record) for job_record in matched_jobs]

    async def create_run(self, job_id: str, status: str) -> str:
        self._run_counter += 1
        run_id = f"run-{self._run_counter}"
        self.created_runs.append(
            {
                "run_id": run_id,
                "job_id": job_id,
                "status": status,
            }
        )
        return run_id

    async def complete_run(  # noqa: WPS211 - mirrors production API signature
        self,
        run_id: str,
        status: str,
        **changes: Unpack[CompleteRunChanges],
    ) -> bool:
        self.completed_runs.append(
            {
                "run_id": run_id,
                "status": status,
                **changes,
            }
        )
        return True

    async def get_job_by_id(
        self,
        job_id: str,
    ) -> dict[str, object] | None:
        job = self.jobs_by_id.get(job_id)
        return None if job is None else dict(job)

    async def update_job(self, name: str, **changes: object) -> bool:
        for job in self.jobs_by_id.values():
            if str(job["name"]) != name:
                continue
            job.update(changes)
            update_record: dict[str, object] = {"name": name}
            update_record.update(changes)
            self.update_calls.append(update_record)
            return True
        return False

    async def delete_job(self, name: str) -> bool:
        ids = _ids_by_name(self.jobs_by_id, name)
        if not ids:
            return False
        for jid in ids:
            self.jobs_by_id.pop(jid, None)
        self.deleted_jobs.append(name)
        return True


def _is_enabled(job: dict[str, object]) -> bool:
    return bool(job.get("enabled", True))


def _ids_by_name(
    jobs: dict[str, dict[str, object]],
    name: str,
) -> list[str]:
    matching_ids: list[str] = []
    for job_id, job_record in jobs.items():
        if str(job_record.get("name", "")) != name:
            continue
        matching_ids.append(job_id)
    return matching_ids
