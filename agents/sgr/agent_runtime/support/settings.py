"""SGR runtime settings and value normalization."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from core.orchestra_agents.agent_mux_runtime import normalize_float


def normalize_optional_str(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def normalize_int(value: Any, *, default: int, minimum: int = 1) -> int:
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    return max(minimum, int(text))


@dataclass(frozen=True)
class SGRRuntimeSettings:
    threads_url: str | None
    http_endpoint: str
    heartbeat_interval_seconds: float
    guide_view: str
    react_to_inactive: bool
    max_reasoning_steps: int
    max_direct_text_retries: int


def thread_client_timeout_seconds(timeout_seconds: float | None) -> float:
    if timeout_seconds is not None:
        return max(1.0, float(timeout_seconds))
    return max(
        1.0,
        normalize_float(
            os.getenv("ORCHESTRA_THREADS_HTTP_TIMEOUT_SECONDS", "10"),
            default=10.0,
        ),
    )
