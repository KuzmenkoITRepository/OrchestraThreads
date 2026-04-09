"""Tests for agent log analysis config loading."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from core.agent_log_analysis.config import AgentLogAnalysisConfig, load_config

_REQUIRED_DB_URL = "postgresql://test:test@localhost:5432/testdb"


def _load_with_db_url() -> AgentLogAnalysisConfig:
    env = {"AGENT_LOG_ANALYSIS_DATABASE_URL": _REQUIRED_DB_URL}
    with patch.dict(os.environ, env, clear=True):
        return load_config()


class TestLoadConfigConnection(unittest.TestCase):
    """Test connection-related config defaults."""

    def test_host_default(self) -> None:
        cfg = _load_with_db_url()
        self.assertEqual(cfg.host, "0.0.0.0")

    def test_port_default(self) -> None:
        cfg = _load_with_db_url()
        self.assertEqual(cfg.port, 8794)

    def test_database_url(self) -> None:
        cfg = _load_with_db_url()
        self.assertEqual(cfg.database_url, _REQUIRED_DB_URL)

    def test_schema_default(self) -> None:
        cfg = _load_with_db_url()
        self.assertEqual(cfg.db_schema, "agent_log_analysis")

    def test_ingest_token_default_empty(self) -> None:
        cfg = _load_with_db_url()
        self.assertEqual(cfg.ingest_token, "")


class TestLoadConfigQueryDefaults(unittest.TestCase):
    """Test query-related config defaults."""

    def test_page_default(self) -> None:
        cfg = _load_with_db_url()
        self.assertEqual(cfg.query_page_default, 50)

    def test_page_max(self) -> None:
        cfg = _load_with_db_url()
        self.assertEqual(cfg.query_page_max, 200)

    def test_window_hours(self) -> None:
        cfg = _load_with_db_url()
        self.assertEqual(cfg.query_window_hours, 24)


class TestLoadConfigRetentionDefaults(unittest.TestCase):
    """Test retention and limits config defaults."""

    def test_event_retention_days(self) -> None:
        cfg = _load_with_db_url()
        self.assertEqual(cfg.event_retention_days, 30)

    def test_raw_retention_days(self) -> None:
        cfg = _load_with_db_url()
        self.assertEqual(cfg.raw_retention_days, 7)

    def test_max_labels(self) -> None:
        cfg = _load_with_db_url()
        self.assertEqual(cfg.max_labels_per_event, 20)

    def test_max_metadata_bytes(self) -> None:
        cfg = _load_with_db_url()
        self.assertEqual(cfg.max_metadata_bytes, 16384)

    def test_max_raw_payload_bytes(self) -> None:
        cfg = _load_with_db_url()
        self.assertEqual(cfg.max_raw_payload_bytes, 65536)

    def test_max_correlation_nodes(self) -> None:
        cfg = _load_with_db_url()
        self.assertEqual(cfg.max_correlation_nodes, 200)

    def test_max_aggregation_group_keys(self) -> None:
        cfg = _load_with_db_url()
        self.assertEqual(cfg.max_aggregation_group_keys, 3)


class TestLoadConfigRequired(unittest.TestCase):
    """Test required env validation."""

    def test_missing_database_url_raises(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                load_config()

    def test_empty_database_url_raises(self) -> None:
        env = {"AGENT_LOG_ANALYSIS_DATABASE_URL": "  "}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ValueError):
                load_config()


class TestLoadConfigOverrides(unittest.TestCase):
    """Test config loading with custom env values."""

    def test_custom_port_and_schema(self) -> None:
        env = {
            "AGENT_LOG_ANALYSIS_DATABASE_URL": _REQUIRED_DB_URL,
            "AGENT_LOG_ANALYSIS_PORT": "9999",
            "AGENT_LOG_ANALYSIS_DB_SCHEMA": "custom_schema",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = load_config()
        self.assertEqual(cfg.port, 9999)
        self.assertEqual(cfg.db_schema, "custom_schema")

    def test_ingest_token_set(self) -> None:
        env = {
            "AGENT_LOG_ANALYSIS_DATABASE_URL": _REQUIRED_DB_URL,
            "AGENT_LOG_ANALYSIS_INGEST_TOKEN": "my-secret-token",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = load_config()
        self.assertEqual(cfg.ingest_token, "my-secret-token")

    def test_config_is_frozen(self) -> None:
        env = {"AGENT_LOG_ANALYSIS_DATABASE_URL": _REQUIRED_DB_URL}
        with patch.dict(os.environ, env, clear=True):
            cfg = load_config()
        self.assertIsInstance(cfg, AgentLogAnalysisConfig)
        with self.assertRaises(AttributeError):
            cfg.port = 1234  # type: ignore[misc]
