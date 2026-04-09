"""Environment-backed configuration for the agent log analysis service."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentLogAnalysisConfig:
    """Agent log analysis runtime settings."""

    host: str
    port: int
    database_url: str
    db_schema: str
    ingest_token: str
    query_page_default: int
    query_page_max: int
    query_window_hours: int
    event_retention_days: int
    raw_retention_days: int
    max_labels_per_event: int
    max_metadata_bytes: int
    max_raw_payload_bytes: int
    max_raw_message_bytes: int
    max_error_message_bytes: int
    max_correlation_nodes: int
    max_aggregation_group_keys: int


def _require_env(key: str) -> str:
    raw_value = os.getenv(key)
    if raw_value is None or not raw_value.strip():
        raise ValueError(f"Missing required environment variable: {key}")
    return raw_value.strip()


def _int_env(key: str, default: int) -> int:
    raw_value = os.getenv(key, str(default)).strip()
    if not raw_value:
        return default
    return int(raw_value)


def _str_env(key: str, default: str) -> str:
    raw_value = os.getenv(key, default).strip()
    if not raw_value:
        raise ValueError(f"{key} must not be empty")
    return raw_value


def load_config() -> AgentLogAnalysisConfig:
    """Load agent log analysis config from environment variables."""
    return AgentLogAnalysisConfig(
        host=_str_env("AGENT_LOG_ANALYSIS_HOST", "0.0.0.0"),
        port=_int_env("AGENT_LOG_ANALYSIS_PORT", 8794),
        database_url=_require_env("AGENT_LOG_ANALYSIS_DATABASE_URL"),
        db_schema=_str_env("AGENT_LOG_ANALYSIS_DB_SCHEMA", "agent_log_analysis"),
        ingest_token=os.getenv("AGENT_LOG_ANALYSIS_INGEST_TOKEN", "").strip(),
        query_page_default=_int_env("AGENT_LOG_ANALYSIS_QUERY_PAGE_DEFAULT", 50),
        query_page_max=_int_env("AGENT_LOG_ANALYSIS_QUERY_PAGE_MAX", 200),
        query_window_hours=_int_env("AGENT_LOG_ANALYSIS_QUERY_WINDOW_HOURS", 24),
        event_retention_days=_int_env("AGENT_LOG_ANALYSIS_EVENT_RETENTION_DAYS", 30),
        raw_retention_days=_int_env("AGENT_LOG_ANALYSIS_RAW_RETENTION_DAYS", 7),
        max_labels_per_event=_int_env("AGENT_LOG_ANALYSIS_MAX_LABELS_PER_EVENT", 20),
        max_metadata_bytes=_int_env("AGENT_LOG_ANALYSIS_MAX_METADATA_BYTES", 16384),
        max_raw_payload_bytes=_int_env("AGENT_LOG_ANALYSIS_MAX_RAW_PAYLOAD_BYTES", 65536),
        max_raw_message_bytes=_int_env("AGENT_LOG_ANALYSIS_MAX_RAW_MESSAGE_BYTES", 16384),
        max_error_message_bytes=_int_env("AGENT_LOG_ANALYSIS_MAX_ERROR_MESSAGE_BYTES", 4096),
        max_correlation_nodes=_int_env("AGENT_LOG_ANALYSIS_MAX_CORRELATION_NODES", 200),
        max_aggregation_group_keys=_int_env(
            "AGENT_LOG_ANALYSIS_MAX_AGGREGATION_GROUP_KEYS",
            3,
        ),
    )
