from __future__ import annotations

JOB_TYPES: tuple[str, ...] = ("cron", "date")
ACTION_TYPES: tuple[str, ...] = ("agent_event", "scheduler_wakeup")
MISFIRE_POLICIES: tuple[str, ...] = ("skip", "coalesce", "run_all")
RUN_STATUSES: tuple[str, ...] = ("running", "success", "failed")
DEFAULT_LIST_LIMIT = 100
DEFAULT_HISTORY_LIMIT = 50


class SchedulerCronError(RuntimeError):
    __slots__ = ()


def ensure_choice(raw_value: str, *, field: str, allowed: tuple[str, ...]) -> str:
    normalized = str(raw_value or "").strip()
    if normalized not in allowed:
        allowed_values = ", ".join(allowed)
        raise SchedulerCronError(f"{field} must be one of: {allowed_values}")
    return normalized
