from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module
from typing import Any, cast

MISFIRE_SKIP = "skip"
MISFIRE_COALESCE = "coalesce"
MISFIRE_GRACE_SECONDS = 3600
RUNNING = "running"
SUCCESS = "success"
FAILED = "failed"


def build_scheduler() -> Any:
    scheduler_module = cast(Any, import_module("apscheduler.schedulers.asyncio"))
    jobstores_module = cast(Any, import_module("apscheduler.jobstores.memory"))
    return scheduler_module.AsyncIOScheduler(
        jobstores={"default": jobstores_module.MemoryJobStore()}
    )


def trigger_for(*, job_type: str, schedule: str) -> object:
    if job_type == "cron":
        cron_module = cast(Any, import_module("apscheduler.triggers.cron"))
        return cron_module.CronTrigger.from_crontab(schedule)
    date_module = cast(Any, import_module("apscheduler.triggers.date"))
    return date_module.DateTrigger(run_date=schedule)


def job_args(job: dict[str, object]) -> list[object]:
    return [
        str(job["id"]),
        str(job["action_type"]),
        cast(dict[str, object], job.get("action_payload") or {}),
        bool(job.get("auto_delete", False)),
    ]


def job_options(job: dict[str, object]) -> dict[str, object]:
    misfire_policy = str(job.get("misfire_policy") or MISFIRE_SKIP)
    grace = None if misfire_policy == MISFIRE_SKIP else MISFIRE_GRACE_SECONDS
    return {
        "coalesce": misfire_policy == MISFIRE_COALESCE,
        "misfire_grace_time": grace,
        "replace_existing": True,
    }


def duration_ms(started_at: datetime) -> int:
    return int((datetime.now(UTC) - started_at).total_seconds() * 1000)


def coerce_int(value: object, *, fallback: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return int(value)
        except ValueError:
            return fallback
    return fallback
