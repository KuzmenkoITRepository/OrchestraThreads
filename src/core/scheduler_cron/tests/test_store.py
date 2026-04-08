from __future__ import annotations

import asyncio
import unittest
from typing import Any

import asyncpg

from core.scheduler_cron.common import SchedulerCronError
from core.scheduler_cron.store import SchedulerCronStore
from core.scheduler_cron.tests import store_test_support as store_support


class TestStoreSchemaInit(unittest.TestCase):  # noqa: WPS214 - schema integration checks share one lifecycle-managed fixture class
    """Test store initialization and schema creation."""

    loop: asyncio.AbstractEventLoop
    store: Any
    test_schema: str

    @classmethod
    def setUpClass(cls) -> None:
        cls.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(cls.loop)
        cls.test_schema = store_support.TEST_SCHEMA_PREFIX + store_support.uid()
        cls.store = SchedulerCronStore(
            store_support.database_url(),
            schema_name=cls.test_schema,
        )
        cls.loop.run_until_complete(cls.store.start())

    @classmethod
    def tearDownClass(cls) -> None:
        cls.loop.run_until_complete(store_support.drop_schema(cls.store, cls.test_schema))
        cls.loop.run_until_complete(cls.store.close())
        cls.loop.close()
        asyncio.set_event_loop(None)

    def test_ping_succeeds(self) -> None:
        ok = self.loop.run_until_complete(self.store.ping())
        self.assertTrue(ok)

    def test_tables_exist(self) -> None:
        tables = self.loop.run_until_complete(
            store_support.fetch_table_names(self.store, self.test_schema),
        )
        self.assertIn("scheduler_jobs", tables)
        self.assertIn("scheduler_job_runs", tables)


class TestJobsCrud(unittest.TestCase):  # noqa: WPS214 - CRUD integration cases share one Postgres-backed fixture class
    """Test job CRUD operations against real Postgres."""

    loop: asyncio.AbstractEventLoop
    store: Any
    test_schema: str

    @classmethod
    def setUpClass(cls) -> None:
        cls.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(cls.loop)
        cls.test_schema = store_support.TEST_SCHEMA_PREFIX + store_support.uid()
        cls.store = SchedulerCronStore(
            store_support.database_url(),
            schema_name=cls.test_schema,
        )
        cls.loop.run_until_complete(cls.store.start())

    @classmethod
    def tearDownClass(cls) -> None:
        cls.loop.run_until_complete(store_support.drop_schema(cls.store, cls.test_schema))
        cls.loop.run_until_complete(cls.store.close())
        cls.loop.close()
        asyncio.set_event_loop(None)

    def setUp(self) -> None:
        self._created_names: list[str] = []

    def tearDown(self) -> None:
        self.loop.run_until_complete(
            store_support.cleanup_jobs(self.store, self._created_names),
        )

    def test_create_job_returns_id(self) -> None:
        job_id = self._create_and_track()
        self.assertTrue(job_id)

    def test_get_job_by_name(self) -> None:
        name = f"get-by-name-{store_support.uid()}"
        self._create_and_track(name=name)
        job = self._run(self.store.get_job_by_name(name))
        self.assertIsNotNone(job)
        self.assertEqual(job[store_support.NAME_KEY], name)

    def test_get_job_by_id(self) -> None:
        job_id = self._create_and_track()
        job = self._run(self.store.get_job_by_id(job_id))
        self.assertIsNotNone(job)
        self.assertEqual(job["id"], job_id)

    def test_get_nonexistent_job_returns_none(self) -> None:
        job = self._run(self.store.get_job_by_name("nonexistent-job"))
        self.assertIsNone(job)

    def test_list_jobs_returns_all(self) -> None:
        self._create_and_track(name=f"list-a-{store_support.uid()}")
        self._create_and_track(name=f"list-b-{store_support.uid()}")
        jobs = self._run(self.store.list_jobs())
        self.assertGreaterEqual(len(jobs), 2)  # noqa: WPS432 - explicit count assertion is clearer than a named constant here

    def test_list_jobs_filter_enabled(self) -> None:
        name_on = f"enabled-on-{store_support.uid()}"
        name_off = f"enabled-off-{store_support.uid()}"
        self._create_and_track(name=name_on, enabled=True)
        self._create_and_track(name=name_off, enabled=False)

        enabled = self._run(self.store.list_jobs(enabled=True))
        enabled_names = {str(job[store_support.NAME_KEY]) for job in enabled}
        self.assertIn(name_on, enabled_names)
        self.assertNotIn(name_off, enabled_names)

    def test_update_job_enabled_field(self) -> None:
        name = f"update-{store_support.uid()}"
        self._create_and_track(name=name, enabled=True)
        ok = self._run(self.store.update_job(name, enabled=False))
        self.assertTrue(ok)
        job = self._run(self.store.get_job_by_name(name))
        self.assertFalse(job["enabled"])

    def test_update_job_schedule(self) -> None:
        name = f"update-sched-{store_support.uid()}"
        self._create_and_track(name=name, schedule="*/5 * * * *")
        self._run(self.store.update_job(name, schedule=store_support.DAILY_SCHEDULE))
        job = self._run(self.store.get_job_by_name(name))
        self.assertEqual(job["schedule"], store_support.DAILY_SCHEDULE)

    def test_update_unknown_field_raises(self) -> None:
        name = f"bad-update-{store_support.uid()}"
        self._create_and_track(name=name)
        with self.assertRaises(SchedulerCronError):
            self._run(self.store.update_job(name, bogus_field="x"))

    def test_delete_job(self) -> None:
        name = f"delete-{store_support.uid()}"
        self._create_and_track(name=name)
        ok = self._run(self.store.delete_job(name))
        self.assertTrue(ok)
        self._created_names.remove(name)
        job = self._run(self.store.get_job_by_name(name))
        self.assertIsNone(job)

    def test_delete_nonexistent_returns_false(self) -> None:
        ok = self._run(self.store.delete_job("no-such-job"))
        self.assertFalse(ok)

    def test_create_duplicate_name_raises(self) -> None:
        name = f"dup-{store_support.uid()}"
        self._create_and_track(name=name)
        with self.assertRaises(asyncpg.UniqueViolationError):
            self._create_and_track(name=name)

    def test_invalid_job_type_raises(self) -> None:
        with self.assertRaises(SchedulerCronError):
            self._create_and_track(job_type="invalid")

    def test_invalid_action_type_raises(self) -> None:
        with self.assertRaises(SchedulerCronError):
            self._create_and_track(action_type="invalid")

    def test_date_job_type_accepted(self) -> None:
        job_id = self._create_and_track(
            job_type="date",
            schedule="2030-01-01T00:00:00",
        )
        self.assertTrue(job_id)

    def test_job_fields_persisted(self) -> None:  # noqa: WPS218 - persistence assertion intentionally checks many stored fields together
        name = f"fields-{store_support.uid()}"
        self._create_and_track(
            name=name,
            job_type="cron",
            schedule=store_support.DAILY_SCHEDULE,
            action_type="scheduler_wakeup",
            action_payload={"task": "test"},
            created_by="tester",
            enabled=False,
            auto_delete=True,
            misfire_policy="coalesce",
        )
        job = self._run(self.store.get_job_by_name(name))
        self.assertEqual(job["job_type"], "cron")
        self.assertEqual(job["schedule"], store_support.DAILY_SCHEDULE)
        self.assertEqual(job["action_type"], "scheduler_wakeup")
        self.assertEqual(job["action_payload"], {"task": "test"})
        self.assertEqual(job["created_by"], "tester")
        self.assertFalse(job["enabled"])
        self.assertTrue(job["auto_delete"])
        self.assertEqual(job["misfire_policy"], "coalesce")

    def _run(self, awaitable: Any) -> Any:
        return self.loop.run_until_complete(awaitable)

    def _create_and_track(self, **overrides: Any) -> str:
        kwargs = store_support.job_kwargs(**overrides)
        name = str(kwargs[store_support.NAME_KEY])
        job_id = self._run(self.store.create_job(**kwargs))
        self._created_names.append(name)
        return str(job_id)


class TestRunsCrud(unittest.TestCase):  # noqa: WPS214 - run lifecycle integration cases share one Postgres-backed fixture class
    """Test run lifecycle operations against real Postgres."""

    loop: asyncio.AbstractEventLoop
    store: Any
    test_schema: str
    _job_id: str

    @classmethod
    def setUpClass(cls) -> None:
        cls.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(cls.loop)
        cls.test_schema = store_support.TEST_SCHEMA_PREFIX + store_support.uid()
        cls.store = SchedulerCronStore(
            store_support.database_url(),
            schema_name=cls.test_schema,
        )
        cls.loop.run_until_complete(cls.store.start())
        cls._job_id = cls.loop.run_until_complete(
            cls.store.create_job(**store_support.job_kwargs(name="runs-parent")),
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.loop.run_until_complete(store_support.drop_schema(cls.store, cls.test_schema))
        cls.loop.run_until_complete(cls.store.close())
        cls.loop.close()
        asyncio.set_event_loop(None)

    def test_create_run_returns_id(self) -> None:
        run_id = self._run(self.store.create_run(self._job_id, status=store_support.STATUS_RUNNING))
        self.assertTrue(run_id)

    def test_complete_run_success(self) -> None:
        run_id = self._make_run()
        ok = self._run(
            self.store.complete_run(
                run_id,
                status=store_support.STATUS_SUCCESS,
                result={"ok": True},
                duration_ms=100,
            ),
        )
        self.assertTrue(ok)

    def test_complete_run_failed(self) -> None:
        run_id = self._make_run()
        ok = self._run(
            self.store.complete_run(
                run_id,
                status="failed",
                error_message="boom",
                duration_ms=store_support.FAILED_DURATION_MS,
            ),
        )
        self.assertTrue(ok)

    def test_invalid_run_status_raises(self) -> None:
        with self.assertRaises(SchedulerCronError):
            self._run(self.store.create_run(self._job_id, status="bogus"))

    def test_get_run_history(self) -> None:
        self._run(self.store.create_run(self._job_id, status=store_support.STATUS_RUNNING))
        history = self._run(self.store.get_run_history(self._job_id))
        self.assertGreaterEqual(len(history), 1)

    def test_run_history_filtered_by_status(self) -> None:
        run_id = self._make_run()
        self._run(
            self.store.complete_run(run_id, status=store_support.STATUS_SUCCESS, duration_ms=10),
        )
        success_runs = self._run(
            self.store.get_run_history(self._job_id, status=store_support.STATUS_SUCCESS),
        )
        for run_record in success_runs:
            self.assertEqual(run_record["status"], store_support.STATUS_SUCCESS)

    def test_run_history_respects_limit(self) -> None:
        for _ in range(3):
            self._run(self.store.create_run(self._job_id, status=store_support.STATUS_RUNNING))
        limited = self._run(
            self.store.get_run_history(self._job_id, limit=1),
        )
        self.assertEqual(len(limited), 1)

    def test_cascade_delete_removes_runs(self) -> None:
        """Deleting a job cascades to its runs."""
        kwargs = store_support.job_kwargs(name=f"cascade-{store_support.uid()}")
        cascade_job_id = str(self._run(self.store.create_job(**kwargs)))
        self._run(self.store.create_run(cascade_job_id, status=store_support.STATUS_RUNNING))
        self._run(self.store.delete_job(str(kwargs[store_support.NAME_KEY])))
        history = self._run(self.store.get_run_history(cascade_job_id))
        self.assertEqual(len(history), 0)

    def _run(self, awaitable: Any) -> Any:
        return self.loop.run_until_complete(awaitable)

    def _make_run(self) -> str:
        return str(
            self._run(
                self.store.create_run(self._job_id, status=store_support.STATUS_RUNNING),
            )
        )
