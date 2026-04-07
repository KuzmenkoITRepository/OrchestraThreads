from __future__ import annotations

import asyncio
import os
import unittest
import uuid
from typing import Any

import asyncpg

from core.scheduler_cron.common import SchedulerCronError
from core.scheduler_cron.store import SchedulerCronStore

_TEST_SCHEMA_PREFIX = "scheduler_test_"


def _database_url() -> str:
    return os.getenv(
        "SCHEDULER_CRON_TEST_DATABASE_URL",
        os.getenv(
            "ORCHESTRA_THREADS_TEST_DATABASE_URL",
            "postgresql://orchestra:orchestra@postgres:5432/orchestra_threads",
        ),
    )


def _job_kwargs(
    name: str | None = None,
    **overrides: object,
) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "name": name or f"test-job-{uuid.uuid4().hex[:8]}",
        "job_type": "cron",
        "schedule": "*/5 * * * *",
        "action_type": "agent_event",
        "action_payload": {"target_agent": "sgr", "event_data": {}},
        "created_by": "test-suite",
    }
    defaults.update(overrides)
    return defaults


class TestStoreSchemaInit(unittest.TestCase):  # noqa: WPS214
    """Test store initialization and schema creation."""

    loop: asyncio.AbstractEventLoop
    store: Any
    test_schema: str

    @classmethod
    def setUpClass(cls) -> None:
        cls.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(cls.loop)
        cls.test_schema = _TEST_SCHEMA_PREFIX + uuid.uuid4().hex[:8]
        cls.store = SchedulerCronStore(
            _database_url(),
            schema_name=cls.test_schema,
        )
        cls.loop.run_until_complete(cls.store.start())

    @classmethod
    def tearDownClass(cls) -> None:
        cls.loop.run_until_complete(cls._drop_schema())
        cls.loop.run_until_complete(cls.store.close())
        cls.loop.close()
        asyncio.set_event_loop(None)

    @classmethod
    async def _drop_schema(cls) -> None:
        pool = cls.store.pool
        if pool is None:
            return
        async with pool.acquire() as conn:
            await conn.execute(f'DROP SCHEMA IF EXISTS "{cls.test_schema}" CASCADE')

    def _run(self, awaitable: Any) -> Any:
        return self.loop.run_until_complete(awaitable)

    def test_ping_succeeds(self) -> None:
        ok = self._run(self.store.ping())
        self.assertTrue(ok)

    def test_tables_exist(self) -> None:
        async def _check() -> list[str]:
            pool = self.store.pool
            assert pool is not None
            async with pool.acquire() as conn:
                records = await conn.fetch(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = $1",
                    self.test_schema,
                )
            return sorted(str(row["table_name"]) for row in records)

        tables = self._run(_check())
        self.assertIn("scheduler_jobs", tables)
        self.assertIn("scheduler_job_runs", tables)


class TestJobsCrud(unittest.TestCase):  # noqa: WPS214
    """Test job CRUD operations against real Postgres."""

    loop: asyncio.AbstractEventLoop
    store: Any
    test_schema: str

    @classmethod
    def setUpClass(cls) -> None:
        cls.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(cls.loop)
        cls.test_schema = _TEST_SCHEMA_PREFIX + uuid.uuid4().hex[:8]
        cls.store = SchedulerCronStore(
            _database_url(),
            schema_name=cls.test_schema,
        )
        cls.loop.run_until_complete(cls.store.start())

    @classmethod
    def tearDownClass(cls) -> None:
        cls.loop.run_until_complete(cls._drop_schema())
        cls.loop.run_until_complete(cls.store.close())
        cls.loop.close()
        asyncio.set_event_loop(None)

    @classmethod
    async def _drop_schema(cls) -> None:
        pool = cls.store.pool
        if pool is None:
            return
        async with pool.acquire() as conn:
            await conn.execute(f'DROP SCHEMA IF EXISTS "{cls.test_schema}" CASCADE')

    def setUp(self) -> None:
        self._created_names: list[str] = []

    def tearDown(self) -> None:
        self.loop.run_until_complete(self._cleanup())

    async def _cleanup(self) -> None:
        for name in self._created_names:
            await self.store.delete_job(name)

    def _run(self, awaitable: Any) -> Any:
        return self.loop.run_until_complete(awaitable)

    def _create_and_track(self, **overrides: Any) -> str:
        kwargs = _job_kwargs(**overrides)
        name = str(kwargs["name"])
        job_id = self._run(self.store.create_job(**kwargs))
        self._created_names.append(name)
        return str(job_id)

    def test_create_job_returns_id(self) -> None:
        job_id = self._create_and_track()
        self.assertTrue(job_id)

    def test_get_job_by_name(self) -> None:
        name = f"get-by-name-{uuid.uuid4().hex[:8]}"
        self._create_and_track(name=name)
        job = self._run(self.store.get_job_by_name(name))
        self.assertIsNotNone(job)
        self.assertEqual(job["name"], name)

    def test_get_job_by_id(self) -> None:
        job_id = self._create_and_track()
        job = self._run(self.store.get_job_by_id(job_id))
        self.assertIsNotNone(job)
        self.assertEqual(job["id"], job_id)

    def test_get_nonexistent_job_returns_none(self) -> None:
        job = self._run(self.store.get_job_by_name("nonexistent-job"))
        self.assertIsNone(job)

    def test_list_jobs_returns_all(self) -> None:
        self._create_and_track(name=f"list-a-{uuid.uuid4().hex[:8]}")
        self._create_and_track(name=f"list-b-{uuid.uuid4().hex[:8]}")
        jobs = self._run(self.store.list_jobs())
        self.assertGreaterEqual(len(jobs), 2)  # noqa: WPS432

    def test_list_jobs_filter_enabled(self) -> None:
        name_on = f"enabled-on-{uuid.uuid4().hex[:8]}"
        name_off = f"enabled-off-{uuid.uuid4().hex[:8]}"
        self._create_and_track(name=name_on, enabled=True)
        self._create_and_track(name=name_off, enabled=False)

        enabled = self._run(self.store.list_jobs(enabled=True))
        enabled_names = {str(job["name"]) for job in enabled}
        self.assertIn(name_on, enabled_names)
        self.assertNotIn(name_off, enabled_names)

    def test_update_job_enabled_field(self) -> None:
        name = f"update-{uuid.uuid4().hex[:8]}"
        self._create_and_track(name=name, enabled=True)
        ok = self._run(self.store.update_job(name, enabled=False))
        self.assertTrue(ok)
        job = self._run(self.store.get_job_by_name(name))
        self.assertFalse(job["enabled"])

    def test_update_job_schedule(self) -> None:
        name = f"update-sched-{uuid.uuid4().hex[:8]}"
        self._create_and_track(name=name, schedule="*/5 * * * *")
        self._run(self.store.update_job(name, schedule="0 9 * * *"))
        job = self._run(self.store.get_job_by_name(name))
        self.assertEqual(job["schedule"], "0 9 * * *")

    def test_update_unknown_field_raises(self) -> None:
        name = f"bad-update-{uuid.uuid4().hex[:8]}"
        self._create_and_track(name=name)
        with self.assertRaises(SchedulerCronError):
            self._run(self.store.update_job(name, bogus_field="x"))

    def test_delete_job(self) -> None:
        name = f"delete-{uuid.uuid4().hex[:8]}"
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
        name = f"dup-{uuid.uuid4().hex[:8]}"
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

    def test_job_fields_persisted(self) -> None:  # noqa: WPS218
        name = f"fields-{uuid.uuid4().hex[:8]}"
        self._create_and_track(
            name=name,
            job_type="cron",
            schedule="0 9 * * *",
            action_type="scheduler_wakeup",
            action_payload={"task": "test"},
            created_by="tester",
            enabled=False,
            auto_delete=True,
            misfire_policy="coalesce",
        )
        job = self._run(self.store.get_job_by_name(name))
        self.assertEqual(job["job_type"], "cron")
        self.assertEqual(job["schedule"], "0 9 * * *")
        self.assertEqual(job["action_type"], "scheduler_wakeup")
        self.assertEqual(job["action_payload"], {"task": "test"})
        self.assertEqual(job["created_by"], "tester")
        self.assertFalse(job["enabled"])
        self.assertTrue(job["auto_delete"])
        self.assertEqual(job["misfire_policy"], "coalesce")


class TestRunsCrud(unittest.TestCase):  # noqa: WPS214
    """Test run lifecycle operations against real Postgres."""

    loop: asyncio.AbstractEventLoop
    store: Any
    test_schema: str
    _job_id: str

    @classmethod
    def setUpClass(cls) -> None:
        cls.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(cls.loop)
        cls.test_schema = _TEST_SCHEMA_PREFIX + uuid.uuid4().hex[:8]
        cls.store = SchedulerCronStore(
            _database_url(),
            schema_name=cls.test_schema,
        )
        cls.loop.run_until_complete(cls.store.start())
        cls._job_id = cls.loop.run_until_complete(
            cls.store.create_job(**_job_kwargs(name="runs-parent")),
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.loop.run_until_complete(cls._drop_schema())
        cls.loop.run_until_complete(cls.store.close())
        cls.loop.close()
        asyncio.set_event_loop(None)

    @classmethod
    async def _drop_schema(cls) -> None:
        pool = cls.store.pool
        if pool is None:
            return
        async with pool.acquire() as conn:
            await conn.execute(f'DROP SCHEMA IF EXISTS "{cls.test_schema}" CASCADE')

    def _run(self, awaitable: Any) -> Any:
        return self.loop.run_until_complete(awaitable)

    def test_create_run_returns_id(self) -> None:
        run_id = self._run(self.store.create_run(self._job_id, status="running"))
        self.assertTrue(run_id)

    def test_complete_run_success(self) -> None:
        run_id = str(self._run(self.store.create_run(self._job_id, status="running")))
        ok = self._run(
            self.store.complete_run(
                run_id,
                status="success",
                result={"ok": True},
                duration_ms=100,
            ),
        )
        self.assertTrue(ok)

    def test_complete_run_failed(self) -> None:
        run_id = str(self._run(self.store.create_run(self._job_id, status="running")))
        ok = self._run(
            self.store.complete_run(
                run_id,
                status="failed",
                error_message="boom",
                duration_ms=50,
            ),
        )
        self.assertTrue(ok)

    def test_invalid_run_status_raises(self) -> None:
        with self.assertRaises(SchedulerCronError):
            self._run(self.store.create_run(self._job_id, status="bogus"))

    def test_get_run_history(self) -> None:
        self._run(self.store.create_run(self._job_id, status="running"))
        history = self._run(self.store.get_run_history(self._job_id))
        self.assertGreaterEqual(len(history), 1)

    def test_run_history_filtered_by_status(self) -> None:
        run_id = str(self._run(self.store.create_run(self._job_id, status="running")))
        self._run(
            self.store.complete_run(run_id, status="success", duration_ms=10),
        )
        success_runs = self._run(
            self.store.get_run_history(self._job_id, status="success"),
        )
        for run_record in success_runs:
            self.assertEqual(run_record["status"], "success")

    def test_run_history_respects_limit(self) -> None:
        for _ in range(3):
            self._run(self.store.create_run(self._job_id, status="running"))
        limited = self._run(
            self.store.get_run_history(self._job_id, limit=1),
        )
        self.assertEqual(len(limited), 1)

    def test_cascade_delete_removes_runs(self) -> None:
        """Deleting a job cascades to its runs."""
        kwargs = _job_kwargs(name=f"cascade-{uuid.uuid4().hex[:8]}")
        cascade_job_id = str(self._run(self.store.create_job(**kwargs)))
        self._run(self.store.create_run(cascade_job_id, status="running"))
        self._run(self.store.delete_job(str(kwargs["name"])))
        history = self._run(self.store.get_run_history(cascade_job_id))
        self.assertEqual(len(history), 0)
