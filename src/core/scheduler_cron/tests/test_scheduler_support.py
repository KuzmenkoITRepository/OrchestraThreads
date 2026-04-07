from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from importlib.util import find_spec

from core.scheduler_cron.scheduler_engine_support import (
    MISFIRE_GRACE_SECONDS,
    build_scheduler,
    coerce_int,
    duration_ms,
    job_args,
    job_options,
    trigger_for,
)


def _apscheduler_available() -> bool:
    return find_spec("apscheduler") is not None


class SchedulerEngineSupportTests(unittest.TestCase):
    @unittest.skipUnless(_apscheduler_available(), "apscheduler is not installed")
    def test_build_scheduler_returns_asyncio_scheduler(self) -> None:
        scheduler = build_scheduler()
        class_name = scheduler.__class__.__name__

        self.assertIn("AsyncIOScheduler", class_name)

    @unittest.skipUnless(_apscheduler_available(), "apscheduler is not installed")
    def test_build_scheduler_exposes_expected_scheduler_methods(self) -> None:
        scheduler = build_scheduler()

        self.assertTrue(hasattr(scheduler, "start"))
        self.assertTrue(hasattr(scheduler, "shutdown"))
        self.assertTrue(hasattr(scheduler, "get_jobs"))
        self.assertTrue(hasattr(scheduler, "add_job"))

    @unittest.skipUnless(_apscheduler_available(), "apscheduler is not installed")
    def test_build_scheduler_uses_memory_job_store_as_default(self) -> None:
        scheduler = build_scheduler()
        jobstores_raw = vars(scheduler).get("_jobstores")

        self.assertIsInstance(jobstores_raw, dict)
        jobstores = dict(jobstores_raw)
        self.assertIn("default", jobstores)
        default_store = jobstores["default"]
        self.assertIn("MemoryJobStore", default_store.__class__.__name__)

    @unittest.skipUnless(_apscheduler_available(), "apscheduler is not installed")
    def test_trigger_for_cron_returns_cron_trigger(self) -> None:
        trigger = trigger_for(job_type="cron", schedule="*/5 * * * *")

        self.assertIn("CronTrigger", trigger.__class__.__name__)

    @unittest.skipUnless(_apscheduler_available(), "apscheduler is not installed")
    def test_trigger_for_date_returns_date_trigger(self) -> None:
        trigger = trigger_for(job_type="date", schedule="2025-01-01T00:00:00")

        self.assertIn("DateTrigger", trigger.__class__.__name__)

    def test_job_args_with_payload_and_auto_delete(self) -> None:
        payload: dict[str, object] = {"x": 1, "mode": "full"}
        job: dict[str, object] = {
            "id": "job-1",
            "action_type": "send",
            "action_payload": payload,
            "auto_delete": True,
        }

        args = job_args(job)

        self.assertEqual(args, ["job-1", "send", payload, True])

    def test_job_args_without_payload_or_auto_delete(self) -> None:
        job: dict[str, object] = {
            "id": 77,
            "action_type": "archive",
        }

        args = job_args(job)

        self.assertEqual(args, ["77", "archive", {}, False])

    def test_job_options_skip_policy(self) -> None:
        options = job_options({"misfire_policy": "skip"})

        self.assertEqual(options["coalesce"], False)
        self.assertIsNone(options["misfire_grace_time"])
        self.assertEqual(options["replace_existing"], True)

    def test_job_options_coalesce_policy(self) -> None:
        options = job_options({"misfire_policy": "coalesce"})

        self.assertEqual(options["coalesce"], True)
        self.assertEqual(options["misfire_grace_time"], MISFIRE_GRACE_SECONDS)
        self.assertEqual(options["replace_existing"], True)

    def test_job_options_run_all_policy(self) -> None:
        options = job_options({"misfire_policy": "run_all"})

        self.assertEqual(options["coalesce"], False)
        self.assertEqual(options["misfire_grace_time"], MISFIRE_GRACE_SECONDS)
        self.assertEqual(options["replace_existing"], True)

    def test_duration_ms_returns_positive_int_for_past_time(self) -> None:
        started_at = datetime.now(UTC) - timedelta(milliseconds=20)

        result = duration_ms(started_at)

        self.assertIsInstance(result, int)
        self.assertGreater(result, 0)

    def test_coerce_int_true_is_one(self) -> None:
        self.assertEqual(coerce_int(True), 1)

    def test_coerce_int_false_is_zero(self) -> None:
        self.assertEqual(coerce_int(False), 0)

    def test_coerce_int_int_passthrough(self) -> None:
        self.assertEqual(coerce_int(42), 42)

    def test_coerce_int_valid_str(self) -> None:
        self.assertEqual(coerce_int("123"), 123)

    def test_coerce_int_invalid_str_uses_fallback(self) -> None:
        self.assertEqual(coerce_int("not-a-number", fallback=9), 9)

    def test_coerce_int_none_uses_fallback(self) -> None:
        self.assertEqual(coerce_int(None, fallback=7), 7)

    def test_coerce_int_empty_str_uses_fallback(self) -> None:
        self.assertEqual(coerce_int("   ", fallback=11), 11)


if __name__ == "__main__":
    unittest.main()
