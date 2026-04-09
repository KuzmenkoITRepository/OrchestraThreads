"""Shared support helpers for event-query store tests."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

_TEST_SCHEMA_PREFIX = "ala_query_"
_BASE_TIME = datetime(2025, 1, 1, tzinfo=UTC)
_WINDOW = timedelta(hours=1)


def database_url() -> str:
    """Return the database URL for integration-style store tests."""
    return os.getenv(
        "AGENT_LOG_ANALYSIS_TEST_DATABASE_URL",
        os.getenv(
            "ORCHESTRA_THREADS_TEST_DATABASE_URL",
            "postgresql://orchestra:orchestra@127.0.0.1:5432/orchestra_threads",
        ),
    )


def make_event_row(
    agent_slug: str = "test-agent",
    occurred_at: datetime | None = None,
    event_id: str | None = None,
    status: str = "success",
) -> dict[str, Any]:
    """Build a normalized event row for store tests."""
    return {
        "event_id": event_id or uuid.uuid4().hex,
        "event_type": "inference_event",
        "occurred_at": occurred_at or _BASE_TIME,
        "received_at": _BASE_TIME + timedelta(seconds=1),
        "agent_slug": agent_slug,
        "run_id": "run-1",
        "thread_id": None,
        "correlation_id": "corr-1",
        "parent_event_id": None,
        "status": status,
        "model_name": "gpt-4",
        "provider_name": "openai",
        "request_kind": "chat",
        "action_kind": None,
        "target_name": None,
        "target_agent_slug": None,
        "latency_ms": 120,
        "metadata_json": {},
        "payload_json": {"model": "gpt-4"},
        "raw_payload_attached": False,
    }
