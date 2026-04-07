from __future__ import annotations

import asyncio
import unittest
from collections.abc import Coroutine
from typing import Any
from unittest.mock import patch

from core.scheduler_cron.scheduler_engine_runtime import SchedulerEngine
from core.scheduler_cron.scheduler_engine_support import FAILED, RUNNING, SUCCESS


class FakeScheduledJob:
    def __init__(self, job_id: str) -> None:
        self.id = job_id


class FakeScheduler:
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

    def get_jobs(self) -> list[Any]:
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


class FakeStore:
    def __init__(self, jobs: list[dict[str, object]] | None = None) -> None:
        initial_jobs = jobs or []
        self.jobs_by_id: dict[str, dict[str, object]] = {
            str(job["id"]): dict(job) for job in initial_jobs
        }
        self.runs_by_id: dict[str, dict[str, object]] = {}
        self.created_runs: list[dict[str, str]] = []
        self.completed_runs: list[dict[str, object]] = []
        self.list_jobs_calls: list[bool | None] = []
        self.update_calls: list[dict[str, object]] = []
        self.deleted_jobs: list[str] = []
        self._run_counter = 0

    async def list_jobs(self, enabled: bool | None = None) -> list[dict[str, object]]:
        self.list_jobs_calls.append(enabled)
        if enabled is None:
            return [dict(job) for job in self.jobs_by_id.values()]
        return [
            dict(job)
            for job in self.jobs_by_id.values()
            if bool(job.get("enabled", True)) is enabled
        ]

    async def create_run(self, job_id: str, status: str) -> str:
        self._run_counter += 1
        run_id = f"run-{self._run_counter}"
        payload: dict[str, object] = {"run_id": run_id, "job_id": job_id, "status": status}
        self.created_runs.append({"run_id": run_id, "job_id": job_id, "status": status})
        self.runs_by_id[run_id] = payload
        return run_id

    async def complete_run(
        self,
        run_id: str,
        status: str,
        *,
        result: dict[str, object] | None = None,
        error_message: str | None = None,
        duration_ms: int | None = None,
    ) -> bool:
        completion: dict[str, object] = {
            "run_id": run_id,
            "status": status,
            "result": result,
            "error_message": error_message,
            "duration_ms": duration_ms,
        }
        self.completed_runs.append(completion)
        self.runs_by_id[run_id] = completion
        return True

    async def get_job_by_id(self, job_id: str) -> dict[str, object] | None:
        job = self.jobs_by_id.get(job_id)
        return None if job is None else dict(job)

    async def update_job(self, name: str, **changes: object) -> bool:
        for job in self.jobs_by_id.values():
            if str(job["name"]) == name:
                job.update(changes)
                update_record: dict[str, object] = {"name": name}
                update_record.update(changes)
                self.update_calls.append(update_record)
                return True
        return False

    async def delete_job(self, name: str) -> bool:
        to_delete = [job_id for job_id, job in self.jobs_by_id.items() if str(job["name"]) == name]
        if not to_delete:
            return False
        for job_id in to_delete:
            self.jobs_by_id.pop(job_id, None)
        self.deleted_jobs.append(name)
        return True


class FakeExecutor:
    def __init__(
        self, result: dict[str, object] | None = None, error: Exception | None = None
    ) -> None:
        self.result = result or {"ok": True}
        self.error = error
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def __call__(
        self, action_type: str, action_payload: dict[str, object]
    ) -> dict[str, object]:
        self.calls.append((action_type, action_payload))
        if self.error is not None:
            raise self.error
        return self.result


class SchedulerEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self) -> None:
        pending = [task for task in asyncio.all_tasks(self.loop) if not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        self.loop.close()
        asyncio.set_event_loop(None)

    def run_async(self, coro: Coroutine[Any, Any, Any]) -> Any:
        return self.loop.run_until_complete(coro)

    def test_start_initializes_scheduler_and_begins_sync_loop(self) -> None:
        store = FakeStore([])
        executor = FakeExecutor()
        engine = SchedulerEngine(store, "postgres://unused", executor)
        fake_scheduler = FakeScheduler()

        with patch(
            "core.scheduler_cron.scheduler_engine_runtime.build_scheduler",
            return_value=fake_scheduler,
        ):
            self.run_async(engine.start())

        self.assertTrue(fake_scheduler.started)
        self.assertIs(engine._scheduler, fake_scheduler)
        self.assertIsNotNone(engine._sync_task)
        if engine._sync_task is None:
            self.fail("sync task must be created")
        self.assertFalse(engine._sync_task.done())
        self.assertEqual(store.list_jobs_calls, [True])
        self.run_async(engine.stop())

    def test_stop_shuts_down_scheduler_and_cancels_sync_task(self) -> None:
        store = FakeStore([])
        executor = FakeExecutor()
        engine = SchedulerEngine(store, "postgres://unused", executor)
        fake_scheduler = FakeScheduler()

        with patch(
            "core.scheduler_cron.scheduler_engine_runtime.build_scheduler",
            return_value=fake_scheduler,
        ):
            self.run_async(engine.start())

        original_task = engine._sync_task
        self.run_async(engine.stop())

        self.assertIsNotNone(original_task)
        if original_task is None:
            self.fail("original task must exist")
        self.assertTrue(original_task.done())
        self.assertEqual(fake_scheduler.shutdown_calls, [True])
        self.assertIsNone(engine._scheduler)
        self.assertIsNone(engine._sync_task)

    def test_add_job_registers_job_into_scheduler(self) -> None:
        job = {
            "id": "job-1",
            "name": "first",
            "job_type": "date",
            "schedule": "2026-01-01T00:00:00",
            "action_type": "dispatch",
            "action_payload": {"x": 1},
            "auto_delete": False,
        }
        store = FakeStore([])
        executor = FakeExecutor()
        engine = SchedulerEngine(store, "postgres://unused", executor)
        fake_scheduler = FakeScheduler()

        with patch(
            "core.scheduler_cron.scheduler_engine_runtime.build_scheduler",
            return_value=fake_scheduler,
        ):
            self.run_async(engine.start())

        with (
            patch(
                "core.scheduler_cron.scheduler_engine_runtime.trigger_for",
                return_value="fake-trigger",
            ),
            patch("core.scheduler_cron.scheduler_engine_runtime.job_args", return_value=["arg1"]),
            patch(
                "core.scheduler_cron.scheduler_engine_runtime.job_options",
                return_value={"replace_existing": True},
            ),
        ):
            self.run_async(engine.add_job(job))

        self.assertEqual(len(fake_scheduler.add_job_calls), 1)
        add_call = fake_scheduler.add_job_calls[0]
        self.assertEqual(add_call["id"], "job-1")
        self.assertEqual(add_call["name"], "first")
        self.assertEqual(add_call["trigger"], "fake-trigger")
        self.assertEqual(add_call["args"], ["arg1"])
        self.assertEqual(add_call["func"], engine._job_wrapper)
        self.run_async(engine.stop())

    def test_job_wrapper_success_completes_run_and_increments_run_count(self) -> None:
        store = FakeStore(
            [
                {
                    "id": "job-1",
                    "name": "nightly",
                    "run_count": "2",
                    "failure_count": 0,
                    "enabled": True,
                }
            ]
        )
        executor = FakeExecutor(result={"status": "ok"})
        engine = SchedulerEngine(store, "postgres://unused", executor)

        self.run_async(engine._job_wrapper("job-1", "dispatch", {"k": "v"}, False))

        self.assertEqual(store.created_runs[0]["status"], RUNNING)
        self.assertEqual(store.completed_runs[0]["status"], SUCCESS)
        self.assertEqual(store.completed_runs[0]["result"], {"status": "ok"})
        self.assertEqual(store.jobs_by_id["job-1"]["run_count"], 3)
        self.assertNotIn("job-1", engine._running_jobs)

    def test_job_wrapper_failure_completes_run_increments_failure_and_logs(self) -> None:
        store = FakeStore(
            [
                {
                    "id": "job-2",
                    "name": "failing",
                    "run_count": 0,
                    "failure_count": "1",
                    "enabled": True,
                }
            ]
        )
        executor = FakeExecutor(error=RuntimeError("boom"))
        engine = SchedulerEngine(store, "postgres://unused", executor)

        with self.assertLogs("core.scheduler_cron.scheduler_engine_runtime", level="ERROR") as logs:
            self.run_async(engine._job_wrapper("job-2", "dispatch", {"a": 1}, False))

        self.assertEqual(store.created_runs[0]["status"], RUNNING)
        self.assertEqual(store.completed_runs[0]["status"], FAILED)
        self.assertEqual(store.jobs_by_id["job-2"]["failure_count"], 2)
        self.assertTrue(any("Job job-2 failed: boom" in msg for msg in logs.output))
        self.assertNotIn("job-2", engine._running_jobs)

    def test_job_wrapper_auto_delete_removes_scheduler_job_and_store_job(self) -> None:
        store = FakeStore(
            [
                {
                    "id": "job-3",
                    "name": "one-shot",
                    "run_count": 0,
                    "failure_count": 0,
                    "enabled": True,
                }
            ]
        )
        executor = FakeExecutor(result={"done": True})
        engine = SchedulerEngine(store, "postgres://unused", executor)
        fake_scheduler = FakeScheduler()
        engine._scheduler = fake_scheduler

        self.run_async(engine._job_wrapper("job-3", "dispatch", {}, True))

        self.assertEqual(store.completed_runs[0]["status"], SUCCESS)
        self.assertEqual(fake_scheduler.remove_job_calls, ["job-3"])
        self.assertEqual(store.deleted_jobs, ["one-shot"])
        self.assertNotIn("job-3", store.jobs_by_id)

    def test_sync_jobs_from_db_adds_missing_jobs_to_scheduler(self) -> None:
        store = FakeStore(
            [
                {
                    "id": "existing-job",
                    "name": "existing",
                    "job_type": "date",
                    "schedule": "2026-01-01T00:00:00",
                    "action_type": "dispatch",
                    "action_payload": {},
                    "enabled": True,
                },
                {
                    "id": "missing-job",
                    "name": "missing",
                    "job_type": "date",
                    "schedule": "2026-01-02T00:00:00",
                    "action_type": "dispatch",
                    "action_payload": {},
                    "enabled": True,
                },
            ]
        )
        executor = FakeExecutor()
        engine = SchedulerEngine(store, "postgres://unused", executor)
        fake_scheduler = FakeScheduler()
        fake_scheduler.seed_job_ids(["existing-job"])
        engine._scheduler = fake_scheduler

        with (
            patch(
                "core.scheduler_cron.scheduler_engine_runtime.trigger_for",
                return_value="fake-trigger",
            ),
            patch("core.scheduler_cron.scheduler_engine_runtime.job_args", return_value=["arg1"]),
            patch(
                "core.scheduler_cron.scheduler_engine_runtime.job_options",
                return_value={"replace_existing": True},
            ),
        ):
            self.run_async(engine._sync_jobs_from_db())

        self.assertEqual(store.list_jobs_calls, [True])
        self.assertEqual(len(fake_scheduler.add_job_calls), 1)
        self.assertEqual(fake_scheduler.add_job_calls[0]["id"], "missing-job")

    def test_remove_pause_resume_delegate_to_scheduler(self) -> None:
        store = FakeStore([])
        executor = FakeExecutor()
        engine = SchedulerEngine(store, "postgres://unused", executor)
        fake_scheduler = FakeScheduler()
        engine._scheduler = fake_scheduler

        removed = self.run_async(engine.remove_job("job-a"))
        paused = self.run_async(engine.pause_job("job-a"))
        resumed = self.run_async(engine.resume_job("job-a"))

        self.assertTrue(removed)
        self.assertTrue(paused)
        self.assertTrue(resumed)
        self.assertEqual(fake_scheduler.remove_job_calls, ["job-a"])
        self.assertEqual(fake_scheduler.pause_job_calls, ["job-a"])
        self.assertEqual(fake_scheduler.resume_job_calls, ["job-a"])

    def test_remove_pause_resume_return_false_without_scheduler(self) -> None:
        store = FakeStore([])
        executor = FakeExecutor()
        engine = SchedulerEngine(store, "postgres://unused", executor)

        self.assertFalse(self.run_async(engine.remove_job("job-x")))
        self.assertFalse(self.run_async(engine.pause_job("job-x")))
        self.assertFalse(self.run_async(engine.resume_job("job-x")))

    def test_failure_error_message_is_truncated_to_1024_chars(self) -> None:
        long_error = "x" * 2000
        store = FakeStore(
            [
                {
                    "id": "job-4",
                    "name": "truncate-error",
                    "run_count": 0,
                    "failure_count": 0,
                    "enabled": True,
                }
            ]
        )
        executor = FakeExecutor(error=RuntimeError(long_error))
        engine = SchedulerEngine(store, "postgres://unused", executor)

        self.run_async(engine._job_wrapper("job-4", "dispatch", {}, False))

        error_message = store.completed_runs[0]["error_message"]
        self.assertIsInstance(error_message, str)
        self.assertEqual(len(str(error_message)), 1024)
        self.assertEqual(str(error_message), long_error[:1024])

    def test_stop_without_start_is_safe_noop(self) -> None:
        store = FakeStore([])
        executor = FakeExecutor()
        engine = SchedulerEngine(store, "postgres://unused", executor)

        self.run_async(engine.stop())

        self.assertIsNone(engine._scheduler)
        self.assertIsNone(engine._sync_task)

    def test_stop_waits_for_running_jobs_to_finish(self) -> None:
        store = FakeStore([])
        executor = FakeExecutor()
        engine = SchedulerEngine(store, "postgres://unused", executor)
        fake_scheduler = FakeScheduler()
        engine._scheduler = fake_scheduler

        async def finish_job() -> None:
            await asyncio.sleep(0.01)
            engine._running_jobs.pop("job-1", None)

        engine._running_jobs["job-1"] = "run-1"
        self.loop.create_task(finish_job())

        self.run_async(engine.stop())

        self.assertEqual(fake_scheduler.shutdown_calls, [True])
        self.assertEqual(engine._running_jobs, {})


if __name__ == "__main__":
    unittest.main()
