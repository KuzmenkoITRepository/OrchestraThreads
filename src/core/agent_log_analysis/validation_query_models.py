"""Typed query validation results."""

from __future__ import annotations

from dataclasses import dataclass

from core.agent_log_analysis.raw_log_models import RawLogLevel
from core.agent_log_analysis.store_raw_logs import RawLogQueryParams


@dataclass(frozen=True)
class ValidatedRawLogQuery:
    """Validated raw-log query preserving extra raw-log filters."""

    store_params: RawLogQueryParams
    event_id: str | None = None
    level: RawLogLevel | None = None
    source: str | None = None
