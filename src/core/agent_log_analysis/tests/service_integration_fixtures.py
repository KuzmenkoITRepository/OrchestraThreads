"""Fixtures for agent log analysis integration tests."""

from __future__ import annotations

import os

from core.agent_log_analysis.config import AgentLogAnalysisConfig

TEST_SCHEMA_PREFIX = "ala_svc_"


def database_url() -> str:
    """Resolve the integration-test database URL."""
    return os.getenv(
        "AGENT_LOG_ANALYSIS_TEST_DATABASE_URL",
        os.getenv(
            "ORCHESTRA_THREADS_TEST_DATABASE_URL",
            "postgresql://orchestra:orchestra@127.0.0.1:5432/orchestra_threads",
        ),
    )


async def drop_schema_by_name(schema: str) -> None:
    """Drop one disposable schema after integration tests."""
    import asyncpg  # noqa: WPS433 - local import keeps DB dependency scoped to teardown helper

    conn = await asyncpg.connect(database_url())
    try:  # noqa: WPS501 - connection must always be closed
        await conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
    finally:
        await conn.close()


def config(schema: str) -> AgentLogAnalysisConfig:
    """Build a real service config for one disposable schema."""
    return AgentLogAnalysisConfig(
        host="127.0.0.1",
        port=0,
        database_url=database_url(),
        db_schema=schema,
        ingest_token="",
        query_page_default=50,
        query_page_max=200,
        query_window_hours=24,
        event_retention_days=30,
        raw_retention_days=7,
        max_labels_per_event=20,
        max_metadata_bytes=16384,
        max_raw_payload_bytes=65536,
        max_raw_message_bytes=16384,
        max_error_message_bytes=4096,
        max_correlation_nodes=200,
        max_aggregation_group_keys=3,
    )


def sample_event_payload() -> dict[str, object]:
    """Return one canonical ingest payload for parity checks."""
    return {
        "event_id": "evt-1",
        "event_type": "inference_event",
        "occurred_at": "2025-01-01T00:00:00Z",
        "agent_slug": "agent-a",
        "run_id": "run-1",
        "thread_id": "thread-1",
        "correlation_id": "corr-1",
        "labels": {"phase": "run"},
        "metadata": {"seq": 1},
        "raw_payload": {"provider": "openai"},
        "inference": {
            "model_name": "gpt-4o",
            "provider_name": "openai",
            "request_kind": "chat",
            "status": "success",
            "latency_ms": 12,
        },
        "raw_logs": [
            {
                "occurred_at": "2025-01-01T00:00:00Z",
                "level": "INFO",
                "raw_message": "message-1",
                "source": "stdout",
                "raw_payload_json": {"idx": 1},
            }
        ],
    }


def analysis_payloads() -> dict[str, dict[str, object]]:
    """Return the runtime analysis payloads for one canonical dataset."""
    return {
        "query": {
            "agent_slug": "agent-a",
            "window_start": "2025-01-01T00:00:00Z",
            "window_end": "2025-01-01T01:00:00Z",
            "run_id": "run-1",
            "thread_id": "thread-1",
            "correlation_id": "corr-1",
            "limit": 10,
        },
        "timeline": {
            "agent_slug": "agent-a",
            "window_start": "2025-01-01T00:00:00Z",
            "window_end": "2025-01-01T01:00:00Z",
            "run_id": "run-1",
            "thread_id": "thread-1",
            "limit": 10,
        },
        "correlation": {
            "agent_slug": "agent-a",
            "correlation_id": "corr-1",
            "run_id": "run-1",
            "thread_id": "thread-1",
        },
        "aggregate": {
            "agent_slug": "agent-a",
            "window_start": "2025-01-01T00:00:00Z",
            "window_end": "2025-01-01T01:00:00Z",
            "group_by": ["status"],
            "metrics": ["count"],
        },
        "raw_logs": {
            "agent_slug": "agent-a",
            "window_start": "2025-01-01T00:00:00Z",
            "window_end": "2025-01-01T01:00:00Z",
            "run_id": "run-1",
            "thread_id": "thread-1",
            "correlation_id": "corr-1",
            "event_id": "evt-1",
            "level": "INFO",
            "source": "stdout",
            "limit": 10,
        },
    }
