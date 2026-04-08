"""Shared helpers and constants for scheduler_cron store integration tests."""  # noqa: WPS202 - intentional support module collecting shared test symbols

from __future__ import annotations

import os
import uuid
from typing import Any

TEST_SCHEMA_PREFIX = "scheduler_test_"
NAME_KEY = "name"
DAILY_SCHEDULE = "0 9 * * *"
STATUS_RUNNING = "running"
STATUS_SUCCESS = "success"
FAILED_DURATION_MS = 50


def uid() -> str:
    return uuid.uuid4().hex[:8]


def database_url() -> str:
    return os.getenv(
        "SCHEDULER_CRON_TEST_DATABASE_URL",
        os.getenv(
            "ORCHESTRA_THREADS_TEST_DATABASE_URL",
            "postgresql://orchestra:orchestra@postgres:5432/orchestra_threads",
        ),
    )


def job_kwargs(
    name: str | None = None,
    **overrides: object,
) -> dict[str, Any]:
    """Build default job creation kwargs with optional overrides."""
    defaults: dict[str, Any] = {
        NAME_KEY: name or f"test-job-{uid()}",
        "job_type": "cron",
        "schedule": "*/5 * * * *",
        "action_type": "agent_event",
        "action_payload": {"target_agent": "sgr", "event_data": {}},
        "created_by": "test-suite",
    }
    defaults.update(overrides)
    return defaults


async def drop_schema(store: Any, schema: str) -> None:
    """Drop a test schema if pool is available."""
    pool = store.pool
    if pool is None:
        return
    async with pool.acquire() as conn:
        await conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


async def fetch_table_names(store: Any, schema: str) -> list[str]:
    """Return sorted table names for a given schema."""
    pool = store.pool
    assert pool is not None  # noqa: S101
    async with pool.acquire() as conn:
        records = await conn.fetch(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = $1",
            schema,
        )
    return sorted(str(row["table_name"]) for row in records)


async def cleanup_jobs(store: Any, names: list[str]) -> None:
    """Delete jobs by name for test teardown."""
    for name in names:  # noqa: WPS476 - sequential cleanup is intentional for test isolation
        await store.delete_job(name)  # noqa: WPS476
