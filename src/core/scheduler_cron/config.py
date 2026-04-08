from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class SchedulerCronConfig:
    host: str
    port: int
    database_url: str
    db_schema: str


def _require_env(key: str) -> str:
    raw_value = os.getenv(key)
    if raw_value is None or not raw_value.strip():
        raise ValueError(f"Missing required environment variable: {key}")
    return raw_value.strip()


def load_config() -> SchedulerCronConfig:
    host = os.getenv("SCHEDULER_CRON_HOST", "0.0.0.0").strip()
    if not host:
        raise ValueError("SCHEDULER_CRON_HOST must not be empty")

    port_raw = os.getenv("SCHEDULER_CRON_PORT", "8792").strip()
    if not port_raw:
        raise ValueError("SCHEDULER_CRON_PORT must not be empty")

    schema = os.getenv("SCHEDULER_CRON_DB_SCHEMA", "public").strip()
    if not schema:
        raise ValueError("SCHEDULER_CRON_DB_SCHEMA must not be empty")

    return SchedulerCronConfig(
        host=host,
        port=int(port_raw),
        database_url=_require_env("SCHEDULER_CRON_DATABASE_URL"),
        db_schema=schema,
    )
