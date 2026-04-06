"""Environment-backed configuration for the task registry service."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class TaskRegistryConfig:
    """Task registry runtime settings."""

    host: str
    port: int
    database_url: str


def _require_env(key: str) -> str:
    value = os.getenv(key)
    if value is None or not value.strip():
        raise ValueError(f"Missing required environment variable: {key}")
    return value.strip()


def load_config() -> TaskRegistryConfig:
    """Load task registry config from environment variables."""
    host = os.getenv("TASK_REGISTRY_HOST", "0.0.0.0").strip()
    if not host:
        raise ValueError("TASK_REGISTRY_HOST must not be empty")

    port_raw = os.getenv("TASK_REGISTRY_PORT", "8791").strip()
    if not port_raw:
        raise ValueError("TASK_REGISTRY_PORT must not be empty")

    return TaskRegistryConfig(
        host=host,
        port=int(port_raw),
        database_url=_require_env("TASK_REGISTRY_DATABASE_URL"),
    )
