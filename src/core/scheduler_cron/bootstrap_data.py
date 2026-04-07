from __future__ import annotations

SCHEDULER_WAKEUP = "scheduler_wakeup"
AGENT_EVENT = "agent_event"
SYSTEM_USER = "system"
TARGET_AGENT = "sgr"


def _scheduler_wakeup_payload(task: str) -> dict[str, object]:
    return {"task": task, "context": {}, "target_agent": TARGET_AGENT}


def _agent_event_payload() -> dict[str, object]:
    return {
        "target_agent": TARGET_AGENT,
        "event_data": {"type": "health_check", "timestamp": None},
    }


def job_definitions() -> tuple[dict[str, object], ...]:
    return (
        {
            "name": "overdue-check",
            "job_type": "cron",
            "schedule": "0 9 * * *",
            "action_type": SCHEDULER_WAKEUP,
            "action_payload": _scheduler_wakeup_payload("check_overdue_tasks"),
            "enabled": True,
            "auto_delete": False,
            "misfire_policy": "skip",
            "created_by": SYSTEM_USER,
        },
        {
            "name": "health-check",
            "job_type": "cron",
            "schedule": "*/15 * * * *",
            "action_type": AGENT_EVENT,
            "action_payload": _agent_event_payload(),
            "enabled": True,
            "auto_delete": False,
            "misfire_policy": "skip",
            "created_by": SYSTEM_USER,
        },
        {
            "name": "weekly-summary",
            "job_type": "cron",
            "schedule": "0 8 * * 1",
            "action_type": SCHEDULER_WAKEUP,
            "action_payload": _scheduler_wakeup_payload("generate_weekly_summary"),
            "enabled": True,
            "auto_delete": False,
            "misfire_policy": "skip",
            "created_by": SYSTEM_USER,
        },
    )
