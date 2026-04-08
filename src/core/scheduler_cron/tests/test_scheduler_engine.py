from __future__ import annotations

import asyncio
import unittest
from collections.abc import Coroutine
from typing import Any

from core.scheduler_cron.scheduler_engine_runtime import SchedulerEngine
from core.scheduler_cron.scheduler_engine_support import FAILED, RUNNING, SUCCESS
from core.scheduler_cron.tests.engine_fake_store import FakeStore
from core.scheduler_cron.tests.engine_fakes import FakeExecutor, FakeScheduler
from core.scheduler_cron.tests.engine_test_support import (
    ERROR_LIMIT,
    cancel_pending,
    engine_with_job,
    full_job,
    make_engine,
    patched_helpers,
    start_engine,
)

_JOB_ONE_ID = "job-1"
_DISPATCH_ACTION = "dispatch"
_LONG_ERROR_CHAR = "x"
_LONG_ERROR_LENGTH = 2000
_MISSING_JOB_ID = "missing-job"
_CONTROL_JOB_ID = "x"


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self) -> None:
        cancel_pending(self.loop)
        self.loop.close()
        asyncio.set_event_loop(None)

    def go(self, coro: Coroutine[Any, Any, Any]) -> Any:
        return self.loop.run_until_complete(coro)


class TestStartStop(_Base):
    def test_start_initializes(self) -> None:
        engine, sched = start_engine(self.go)
        self.assertTrue(sched.started)
        self.assertIsNotNone(engine._sync_task)
        self.go(engine.stop())

    def test_stop_cancels_task(self) -> None:
        engine, sched = start_engine(self.go)
        task = engine._sync_task
        self.go(engine.stop())
        self.assertIsNotNone(task)
        if task is not None:
            self.assertTrue(task.done())
        self.assertEqual(sched.shutdown_calls, [True])

    def test_stop_without_start(self) -> None:
        engine = make_engine()
        self.go(engine.stop())
        self.assertIsNone(engine._scheduler)


class TestAddJob(_Base):
    def test_registers_in_scheduler(self) -> None:
        engine, sched = start_engine(self.go)

        with patched_helpers():
            self.go(engine.add_job(full_job(_JOB_ONE_ID, "first")))

        call = sched.add_job_calls[0]
        self.assertEqual(call["id"], _JOB_ONE_ID)
        self.assertEqual(call["func"], engine._job_wrapper)
        self.go(engine.stop())


class TestJobWrapper(_Base):
    def test_success_run(self) -> None:
        store, engine = engine_with_job(_JOB_ONE_ID, "nightly", run_count="2")
        self.go(engine._job_wrapper(_JOB_ONE_ID, _DISPATCH_ACTION, {}, False))

        self.assertEqual(store.created_runs[0]["status"], RUNNING)
        self.assertEqual(store.completed_runs[0]["status"], SUCCESS)

    def test_failure_logs(self) -> None:
        store, engine = engine_with_job(
            "job-2",
            "failing",
            executor=FakeExecutor(error=RuntimeError("boom")),
        )
        log_name = "core.scheduler_cron.scheduler_engine_runtime"

        with self.assertLogs(log_name, level="ERROR") as ctx:
            self.go(engine._job_wrapper("job-2", _DISPATCH_ACTION, {}, False))
            has_boom = any("boom" in log_message for log_message in ctx.output)

        self.assertEqual(store.completed_runs[0]["status"], FAILED)
        self.assertTrue(has_boom)

    def test_auto_delete(self) -> None:
        store, engine = engine_with_job("job-3", "one-shot")
        engine._scheduler = FakeScheduler()
        self.go(engine._job_wrapper("job-3", _DISPATCH_ACTION, {}, True))
        self.assertEqual(store.deleted_jobs, ["one-shot"])

    def test_error_truncated(self) -> None:
        long_err = _LONG_ERROR_CHAR * _LONG_ERROR_LENGTH
        store, engine = engine_with_job(
            "job-4",
            "trunc",
            executor=FakeExecutor(error=RuntimeError(long_err)),
        )
        self.go(engine._job_wrapper("job-4", _DISPATCH_ACTION, {}, False))
        msg = str(store.completed_runs[0]["error_message"])
        self.assertEqual(len(msg), ERROR_LIMIT)


class TestSyncAndControl(_Base):  # noqa: WPS214 - sync and control ops tested together share one engine-lifecycle fixture
    def test_sync_adds_missing(self) -> None:
        store, engine = _setup_sync_engine()

        with patched_helpers():
            self.go(engine._sync_jobs_from_db())

        sched = engine._scheduler
        self.assertIsNotNone(sched)
        if isinstance(sched, FakeScheduler):
            self.assertEqual(sched.add_job_calls[0]["id"], _MISSING_JOB_ID)

    def test_control_delegates(self) -> None:
        engine = make_engine()
        engine._scheduler = FakeScheduler()
        self.assertTrue(self.go(engine.remove_job("j")))
        self.assertTrue(self.go(engine.pause_job("j")))
        self.assertTrue(self.go(engine.resume_job("j")))

    def test_control_false_without_scheduler(self) -> None:
        engine = make_engine()
        self.assertFalse(self.go(engine.remove_job(_CONTROL_JOB_ID)))
        self.assertFalse(self.go(engine.pause_job(_CONTROL_JOB_ID)))
        self.assertFalse(self.go(engine.resume_job(_CONTROL_JOB_ID)))

    def test_stop_waits_for_running_jobs_to_finish(self) -> None:
        store = FakeStore([])
        executor = FakeExecutor()
        engine = SchedulerEngine(store, "postgres://unused", executor)
        fake_scheduler = FakeScheduler()
        engine._scheduler = fake_scheduler

        engine._running_jobs["job-1"] = "run-1"
        self.loop.create_task(_finish_job_after_delay(engine))

        self.go(engine.stop())

        self.assertEqual(fake_scheduler.shutdown_calls, [True])
        self.assertEqual(engine._running_jobs, {})


async def _finish_job_after_delay(engine: SchedulerEngine) -> None:
    await asyncio.sleep(0.01)
    engine._running_jobs.pop("job-1", None)


def _setup_sync_engine() -> tuple[Any, Any]:
    from core.scheduler_cron.tests.engine_fake_store import FakeStore as FS  # noqa: WPS433,N813

    store = FS([full_job("existing-job", "existing"), full_job(_MISSING_JOB_ID, "missing")])
    engine = make_engine(store=store)
    sched = FakeScheduler()
    sched.seed_job_ids(["existing-job"])
    engine._scheduler = sched
    return store, engine


if __name__ == "__main__":
    unittest.main()
