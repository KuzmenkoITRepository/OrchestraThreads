"""Raw log record models for agent telemetry."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class RawLogLevel(StrEnum):
    """Log level for raw log records."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class RawLogRecord:
    """One raw log record."""

    log_id: int
    event_id: str | None
    occurred_at: datetime
    received_at: datetime
    agent_slug: str
    run_id: str | None
    thread_id: str | None
    correlation_id: str | None
    source: str | None
    level: RawLogLevel
    raw_message: str
    raw_payload_json: dict[str, Any] | None = None


@dataclass(frozen=True)
class RawLogPage:
    """Paginated raw log response."""

    agent_slug: str
    items: list[RawLogRecord]
    next_cursor: str | None = None
