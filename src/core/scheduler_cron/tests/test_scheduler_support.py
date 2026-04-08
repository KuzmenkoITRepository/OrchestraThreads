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

_SKIP_MSG = "apscheduler is not installed"

_COALESCE_KEY = "coalesce"
_ELAPSED_MS = 20
_SAMPLE_INT = 42
_PARSED_INT = 123
_FALLBACK_EMPTY = 11


def _has_apscheduler() -> bool:
    return find_spec("apscheduler") is not None


class TestBuildScheduler(unittest.TestCase):
    @unittest.skipUnless(_has_apscheduler(), _SKIP_MSG)
    def test_returns_asyncio_scheduler(self) -> None:
        scheduler = build_scheduler()
        self.assertIn("AsyncIOScheduler", type(scheduler).__name__)

    @unittest.skipUnless(_has_apscheduler(), _SKIP_MSG)
    def test_exposes_expected_methods(self) -> None:
        scheduler = build_scheduler()

        self.assertTrue(hasattr(scheduler, "start"))
        self.assertTrue(hasattr(scheduler, "shutdown"))
        self.assertTrue(hasattr(scheduler, "get_jobs"))
        self.assertTrue(hasattr(scheduler, "add_job"))

    @unittest.skipUnless(_has_apscheduler(), _SKIP_MSG)
    def test_uses_memory_job_store(self) -> None:
        scheduler = build_scheduler()
        jobstores = scheduler.__dict__.get("_jobstores", {})

        self.assertIsInstance(jobstores, dict)
        self.assertIn("default", jobstores)
        default_store = jobstores["default"]
        self.assertIn("MemoryJobStore", type(default_store).__name__)

    @unittest.skipUnless(_has_apscheduler(), _SKIP_MSG)
    def test_cron_trigger(self) -> None:
        trigger = trigger_for(job_type="cron", schedule="*/5 * * * *")
        self.assertIn("CronTrigger", type(trigger).__name__)

    @unittest.skipUnless(_has_apscheduler(), _SKIP_MSG)
    def test_date_trigger(self) -> None:
        trigger = trigger_for(job_type="date", schedule="2025-01-01T00:00:00")
        self.assertIn("DateTrigger", type(trigger).__name__)


class TestJobArgs(unittest.TestCase):
    def test_with_payload_and_auto_delete(self) -> None:
        payload: dict[str, object] = {"x": 1, "mode": "full"}
        job: dict[str, object] = {
            "id": "job-1",
            "action_type": "send",
            "action_payload": payload,
            "auto_delete": True,
        }

        args = job_args(job)

        self.assertEqual(args, ["job-1", "send", payload, True])

    def test_without_payload_or_auto_delete(self) -> None:
        job: dict[str, object] = {
            "id": 77,
            "action_type": "archive",
        }

        args = job_args(job)

        self.assertEqual(args, ["77", "archive", {}, False])


class TestJobOptions(unittest.TestCase):
    def test_skip_policy(self) -> None:
        options = job_options({"misfire_policy": "skip"})

        self.assertEqual(options[_COALESCE_KEY], False)
        self.assertIsNone(options["misfire_grace_time"])
        self.assertEqual(options["replace_existing"], True)

    def test_coalesce_policy(self) -> None:
        options = job_options({"misfire_policy": "coalesce"})

        self.assertEqual(options[_COALESCE_KEY], True)
        self.assertEqual(options["misfire_grace_time"], MISFIRE_GRACE_SECONDS)
        self.assertEqual(options["replace_existing"], True)

    def test_run_all_policy(self) -> None:
        options = job_options({"misfire_policy": "run_all"})

        self.assertEqual(options[_COALESCE_KEY], False)
        self.assertEqual(options["misfire_grace_time"], MISFIRE_GRACE_SECONDS)
        self.assertEqual(options["replace_existing"], True)


class TestDurationMs(unittest.TestCase):
    def test_positive_int_for_past(self) -> None:
        started_at = datetime.now(UTC) - timedelta(milliseconds=_ELAPSED_MS)

        elapsed = duration_ms(started_at)

        self.assertIsInstance(elapsed, int)
        self.assertGreater(elapsed, 0)


class TestCoerceInt(unittest.TestCase):
    def test_true_is_one(self) -> None:
        self.assertEqual(coerce_int(True), 1)

    def test_false_is_zero(self) -> None:
        self.assertEqual(coerce_int(False), 0)

    def test_int_passthrough(self) -> None:
        self.assertEqual(coerce_int(_SAMPLE_INT), _SAMPLE_INT)

    def test_valid_str(self) -> None:
        self.assertEqual(coerce_int("123"), _PARSED_INT)

    def test_invalid_str_uses_fallback(self) -> None:
        self.assertEqual(coerce_int("not-a-number", fallback=9), 9)

    def test_none_uses_fallback(self) -> None:
        self.assertEqual(coerce_int(None, fallback=7), 7)

    def test_empty_str_uses_fallback(self) -> None:
        self.assertEqual(coerce_int("   ", fallback=_FALLBACK_EMPTY), _FALLBACK_EMPTY)


if __name__ == "__main__":
    unittest.main()
