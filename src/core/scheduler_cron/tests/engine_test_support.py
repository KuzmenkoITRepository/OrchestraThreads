"""Shared helpers for scheduler engine tests."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any
from unittest.mock import patch

from core.scheduler_cron.scheduler_engine_runtime import SchedulerEngine
from core.scheduler_cron.tests.engine_fake_store import FakeStore
from core.scheduler_cron.tests.engine_fakes import FakeExecutor, FakeScheduler

_DSN = "postgres://unused"
_BUILD = "core.scheduler_cron.scheduler_engine_runtime.build_scheduler"
_TRIGGER = "core.scheduler_cron.scheduler_engine_runtime.trigger_for"
_ARGS = "core.scheduler_cron.scheduler_engine_runtime.job_args"
_OPTS = "core.scheduler_cron.scheduler_engine_runtime.job_options"
ERROR_LIMIT = 1024


def make_engine(
    store: FakeStore | None = None,
    executor: FakeExecutor | None = None,
) -> SchedulerEngine:
    """Create a SchedulerEngine with optional store/executor."""
    return SchedulerEngine(
        store or FakeStore([]),
        _DSN,
        executor or FakeExecutor(),
    )


def engine_with_job(
    job_id: str,
    name: str,
    *,
    run_count: object = 0,
    executor: FakeExecutor | None = None,
) -> tuple[FakeStore, SchedulerEngine]:
    """Create engine pre-loaded with a single job record."""
    store = FakeStore([job_rec(job_id, name, run_count=run_count)])
    return store, make_engine(store=store, executor=executor)


def start_engine(go: Any) -> tuple[SchedulerEngine, FakeScheduler]:
    """Start engine with patched build_scheduler, return both."""
    engine = make_engine()
    sched = FakeScheduler()
    with patch(_BUILD, return_value=sched):
        go(engine.start())
    return engine, sched


def cancel_pending(loop: asyncio.AbstractEventLoop) -> None:
    """Cancel all pending tasks in the loop."""
    pending = [task_item for task_item in asyncio.all_tasks(loop) if not task_item.done()]
    for t_item in pending:
        t_item.cancel()
    if pending:
        loop.run_until_complete(
            asyncio.gather(*pending, return_exceptions=True),
        )


def patched_helpers() -> contextlib.ExitStack:
    """Context manager stacking trigger/args/options patches."""
    stack = contextlib.ExitStack()
    stack.enter_context(patch(_TRIGGER, return_value="fake-trigger"))
    stack.enter_context(patch(_ARGS, return_value=["arg1"]))
    stack.enter_context(
        patch(_OPTS, return_value={"replace_existing": True}),
    )
    return stack


def job_rec(
    job_id: str,
    name: str,
    *,
    run_count: object = 0,
) -> dict[str, object]:
    """Minimal job record dict."""
    return {
        "id": job_id,
        "name": name,
        "run_count": run_count,
        "failure_count": 0,
        "enabled": True,
    }


def full_job(job_id: str, name: str) -> dict[str, object]:
    """Full job record with all required fields."""
    return {
        "id": job_id,
        "name": name,
        "job_type": "date",
        "schedule": "2026-01-01T00:00:00",
        "action_type": "dispatch",
        "action_payload": {},
        "enabled": True,
    }
