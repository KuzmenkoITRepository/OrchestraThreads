from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_DB_MIN_POOL_SIZE = 5
DEFAULT_DB_MAX_POOL_SIZE = 20
DEFAULT_DB_COMMAND_TIMEOUT_SECONDS = 10
DEFAULT_AGENT_LEASE_SECONDS = 30
DEFAULT_DELIVERY_POLL_INTERVAL_SECONDS = 1
DEFAULT_INACTIVITY_TIMEOUT_SECONDS = 60
DEFAULT_RETRY_BASE_SECONDS = 2
DEFAULT_RETRY_MAX_SECONDS = 30


@dataclass(frozen=True)
class RuntimeConfigOverrides:
    database_url: str | None = None
    database_schema: str | None = None
    db_min_pool_size: int | None = None
    db_max_pool_size: int | None = None
    db_command_timeout_seconds: float | None = None
    agent_lease_seconds: int | None = None
    delivery_poll_interval_seconds: float | None = None
    inactivity_timeout_seconds: int | None = None
    retry_base_seconds: int | None = None
    retry_max_seconds: int | None = None


@dataclass(frozen=True)
class RuntimeConfig:
    database_url: str
    database_schema: str
    db_min_pool_size: int
    db_max_pool_size: int
    db_command_timeout_seconds: float
    agent_lease_seconds: int
    delivery_poll_interval_seconds: float
    inactivity_timeout_seconds: int
    retry_base_seconds: int
    retry_max_seconds: int


def load_runtime_config(overrides: RuntimeConfigOverrides) -> RuntimeConfig:
    db_min_pool_size = _int_setting(
        explicit_value=overrides.db_min_pool_size,
        env_name="ORCHESTRA_THREADS_DB_MIN_POOL_SIZE",
        default=str(DEFAULT_DB_MIN_POOL_SIZE),
        minimum=1,
    )
    retry_base_seconds = _int_setting(
        explicit_value=overrides.retry_base_seconds,
        env_name="ORCHESTRA_THREADS_RETRY_BASE_SECONDS",
        default=str(DEFAULT_RETRY_BASE_SECONDS),
        minimum=1,
    )
    return RuntimeConfig(
        database_url=str(
            overrides.database_url
            or os.getenv("ORCHESTRA_THREADS_DATABASE_URL")
            or "postgresql://orchestra:orchestra@127.0.0.1:5432/orchestra_threads"
        ).strip(),
        database_schema=_schema_value(overrides.database_schema),
        db_min_pool_size=db_min_pool_size,
        db_max_pool_size=_int_setting(
            explicit_value=overrides.db_max_pool_size,
            env_name="ORCHESTRA_THREADS_DB_MAX_POOL_SIZE",
            default=str(DEFAULT_DB_MAX_POOL_SIZE),
            minimum=db_min_pool_size,
        ),
        db_command_timeout_seconds=_float_setting(
            explicit_value=overrides.db_command_timeout_seconds,
            env_name="ORCHESTRA_THREADS_DB_COMMAND_TIMEOUT_SECONDS",
            default=str(DEFAULT_DB_COMMAND_TIMEOUT_SECONDS),
            minimum=1.0,
        ),
        agent_lease_seconds=_int_setting(
            explicit_value=overrides.agent_lease_seconds,
            env_name="ORCHESTRA_THREADS_AGENT_LEASE_SECONDS",
            default=str(DEFAULT_AGENT_LEASE_SECONDS),
            minimum=5,
        ),
        delivery_poll_interval_seconds=_float_setting(
            explicit_value=overrides.delivery_poll_interval_seconds,
            env_name="ORCHESTRA_THREADS_DELIVERY_POLL_INTERVAL_SECONDS",
            default=str(DEFAULT_DELIVERY_POLL_INTERVAL_SECONDS),
            minimum=0.2,
        ),
        inactivity_timeout_seconds=_int_setting(
            explicit_value=overrides.inactivity_timeout_seconds,
            env_name="ORCHESTRA_THREADS_INACTIVITY_TIMEOUT_SECONDS",
            default=str(DEFAULT_INACTIVITY_TIMEOUT_SECONDS),
            minimum=10,
        ),
        retry_base_seconds=retry_base_seconds,
        retry_max_seconds=_int_setting(
            explicit_value=overrides.retry_max_seconds,
            env_name="ORCHESTRA_THREADS_RETRY_MAX_SECONDS",
            default=str(DEFAULT_RETRY_MAX_SECONDS),
            minimum=retry_base_seconds,
        ),
    )


def _schema_value(database_schema: str | None) -> str:
    value = str(database_schema or os.getenv("ORCHESTRA_THREADS_DB_SCHEMA") or "public").strip()
    return value or "public"


def _int_setting(*, explicit_value: int | None, env_name: str, default: str, minimum: int) -> int:
    raw_value = explicit_value or os.getenv(env_name) or default
    return max(minimum, int(raw_value))


def _float_setting(
    *, explicit_value: float | None, env_name: str, default: str, minimum: float
) -> float:
    raw_value = explicit_value or os.getenv(env_name) or default
    return max(minimum, float(raw_value))
