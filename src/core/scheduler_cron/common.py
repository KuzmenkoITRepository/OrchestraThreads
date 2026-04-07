from __future__ import annotations

JOB_TYPES: tuple[str, ...] = ("cron", "date")
ACTION_TYPES: tuple[str, ...] = ("agent_event", "scheduler_wakeup")
MISFIRE_POLICIES: tuple[str, ...] = ("skip", "coalesce", "run_all")
RUN_STATUSES: tuple[str, ...] = ("running", "success", "failed")
DEFAULT_LIST_LIMIT = 100
DEFAULT_HISTORY_LIMIT = 50


class SchedulerCronError(RuntimeError):
    __slots__ = ()


def ensure_choice(value: str, *, field: str, allowed: tuple[str, ...]) -> str:
    normalized = str(value or "").strip()
    if normalized not in allowed:
        raise SchedulerCronError(f"{field} must be one of: {', '.join(allowed)}")
    return normalized
