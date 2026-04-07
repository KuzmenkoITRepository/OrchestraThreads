from __future__ import annotations

import asyncio
import os
import unittest
import uuid
from typing import Any

from core.scheduler_cron.bootstrap_data import job_definitions
from core.scheduler_cron.store import SchedulerCronStore

_TEST_SCHEMA_PREFIX = "scheduler_boot_"

EXPECTED_JOB_NAMES = frozenset({"overdue-check", "health-check", "weekly-summary"})
EXPECTED_JOB_COUNT = 3


def _database_url() -> str:
    return os.getenv(
        "SCHEDULER_CRON_TEST_DATABASE_URL",
        os.getenv(
            "ORCHESTRA_THREADS_TEST_DATABASE_URL",
            "postgresql://orchestra:orchestra@postgres:5432/orchestra_threads",
        ),
    )


class _FakeEngine:
    """Minimal engine stub that records add_job calls."""

    def __init__(self) -> None:
        self.added_jobs: list[dict[str, object]] = []

    async def add_job(self, job: dict[str, object]) -> None:
        self.added_jobs.append(job)


class TestBootstrapData(unittest.TestCase):
    """Test bootstrap_data.job_definitions structure."""

    def test_returns_three_definitions(self) -> None:
        defs = job_definitions()
        self.assertEqual(len(defs), EXPECTED_JOB_COUNT)

    def test_expected_names(self) -> None:
        names = {str(defn["name"]) for defn in job_definitions()}
        self.assertEqual(names, EXPECTED_JOB_NAMES)

    def test_all_cron_type(self) -> None:
        for defn in job_definitions():
            self.assertEqual(defn["job_type"], "cron")

    def test_created_by_system(self) -> None:
        for defn in job_definitions():
            self.assertEqual(defn["created_by"], "system")

    def test_auto_delete_false(self) -> None:
        for defn in job_definitions():
            self.assertFalse(defn["auto_delete"])

    def test_all_enabled(self) -> None:
        for defn in job_definitions():
            self.assertTrue(defn["enabled"])

    def test_valid_action_types(self) -> None:
        valid = {"agent_event", "scheduler_wakeup"}
        for defn in job_definitions():
            self.assertIn(defn["action_type"], valid)


class TestBootstrapOps(unittest.TestCase):  # noqa: WPS214
    """Test bootstrap_jobs against real Postgres with fake engine."""

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
        self._engine = _FakeEngine()

    def tearDown(self) -> None:
        self.loop.run_until_complete(self._delete_all_jobs())

    async def _delete_all_jobs(self) -> None:
        jobs = await self.store.list_jobs()
        for job in jobs:
            await self.store.delete_job(str(job["name"]))

    def _run(self, awaitable: Any) -> Any:
        return self.loop.run_until_complete(awaitable)

    def _bootstrap(self) -> list[str]:
        from core.scheduler_cron.bootstrap_ops import bootstrap_jobs  # noqa: WPS433

        return self._run(bootstrap_jobs(self.store, self._engine))  # type: ignore[no-any-return]  # _run returns Any from run_until_complete

    def test_creates_jobs_on_empty_db(self) -> None:
        created = self._bootstrap()
        self.assertEqual(set(created), EXPECTED_JOB_NAMES)

    def test_jobs_persisted_in_db(self) -> None:
        self._bootstrap()
        jobs = self._run(self.store.list_jobs())
        names = {str(job["name"]) for job in jobs}
        self.assertEqual(names, EXPECTED_JOB_NAMES)

    def test_engine_receives_enabled_jobs(self) -> None:
        self._bootstrap()
        self.assertEqual(len(self._engine.added_jobs), EXPECTED_JOB_COUNT)

    def test_idempotent_second_run(self) -> None:
        self._bootstrap()
        second_engine = _FakeEngine()
        self._engine = second_engine

        created_second = self._bootstrap()
        self.assertEqual(created_second, [])

    def test_refresh_updates_schedule(self) -> None:
        self._bootstrap()
        name = "overdue-check"
        self._run(self.store.update_job(name, schedule="30 10 * * *"))

        second_engine = _FakeEngine()
        self._engine = second_engine
        self._bootstrap()

        job = self._run(self.store.get_job_by_name(name))
        self.assertEqual(job["schedule"], "0 9 * * *")

    def test_refresh_re_adds_to_engine(self) -> None:
        self._bootstrap()
        second_engine = _FakeEngine()
        self._engine = second_engine
        self._bootstrap()
        self.assertEqual(len(second_engine.added_jobs), EXPECTED_JOB_COUNT)
