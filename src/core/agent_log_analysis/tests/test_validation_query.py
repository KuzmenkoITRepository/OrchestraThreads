"""Tests for analytical query validation and ingest auth policy."""

from __future__ import annotations

import unittest
from collections.abc import Callable

from core.agent_log_analysis.config import AgentLogAnalysisConfig
from core.agent_log_analysis.errors import ValidationError
from core.agent_log_analysis.validation_query import QueryValidator


class TestValidateEventAndTimelineQueries(unittest.TestCase):
    """Event and timeline query validation."""

    def setUp(self) -> None:
        self.validator = QueryValidator(_config())

    def test_agent_scope_required(self) -> None:
        _assert_error_code(
            self,
            "AGENT_SCOPE_REQUIRED",
            lambda: self.validator.validate_event_query({"agent_slug": ""}),
        )

    def test_defaults_limit_and_window(self) -> None:
        result = self.validator.validate_timeline_query({"agent_slug": "agent-a"})
        self.assertEqual(result.agent_slug, "agent-a")
        self.assertEqual(result.limit, 50)

    def test_page_limit_cap_enforced(self) -> None:
        _assert_error_code(
            self,
            "PAGE_LIMIT_TOO_LARGE",
            lambda: self.validator.validate_event_query({"agent_slug": "agent-a", "limit": 201}),
        )

    def test_query_window_cap_enforced(self) -> None:
        _assert_error_code(
            self,
            "QUERY_WINDOW_TOO_LARGE",
            lambda: self.validator.validate_event_query(
                {
                    "agent_slug": "agent-a",
                    "window_start": "2025-01-01T00:00:00Z",
                    "window_end": "2025-01-02T01:00:00Z",
                }
            ),
        )


class TestValidateAggregateAndCorrelationQueries(unittest.TestCase):
    """Aggregate and correlation query validation."""

    def setUp(self) -> None:
        self.validator = QueryValidator(_config())

    def test_invalid_group_by_code(self) -> None:
        _assert_error_code(
            self,
            "INVALID_GROUP_BY",
            lambda: self.validator.validate_aggregate_query(
                {
                    "agent_slug": "agent-a",
                    "window_start": "2025-01-01T00:00:00Z",
                    "window_end": "2025-01-01T01:00:00Z",
                    "group_by": ["metadata.foo"],
                }
            ),
        )

    def test_too_many_group_keys_code(self) -> None:
        _assert_error_code(
            self,
            "TOO_MANY_GROUP_KEYS",
            lambda: self.validator.validate_aggregate_query(
                {
                    "agent_slug": "agent-a",
                    "window_start": "2025-01-01T00:00:00Z",
                    "window_end": "2025-01-01T01:00:00Z",
                    "group_by": ["event_type", "status", "provider_name", "model_name"],
                }
            ),
        )

    def test_correlation_query_uses_config_node_cap(self) -> None:
        validator = QueryValidator(_config(max_correlation_nodes=17))
        result = validator.validate_correlation_query(
            {"agent_slug": "agent-a", "correlation_id": "corr-1"}
        )
        self.assertEqual(result.max_nodes, 17)


class TestValidateRawLogQueriesAndAuth(unittest.TestCase):
    """Raw-log query validation and auth policy."""

    def test_raw_log_query_defaults(self) -> None:
        result = QueryValidator(_config()).validate_raw_log_query({"agent_slug": "agent-a"})
        self.assertEqual(result.store_params.agent_slug, "agent-a")
        self.assertEqual(result.store_params.limit, 50)
        self.assertIsNone(result.level)

    def test_auth_disabled_without_token(self) -> None:
        QueryValidator(_config()).validate_ingest_auth(None)

    def test_auth_required_when_token_configured(self) -> None:
        validator = QueryValidator(_config(ingest_token="secret"))
        _assert_error_code(self, "AUTH_REQUIRED", lambda: validator.validate_ingest_auth(None))

    def test_auth_invalid_for_wrong_bearer(self) -> None:
        validator = QueryValidator(_config(ingest_token="secret"))
        _assert_error_code(
            self,
            "AUTH_INVALID",
            lambda: validator.validate_ingest_auth("Bearer nope"),
        )

    def test_auth_accepts_matching_bearer(self) -> None:
        QueryValidator(_config(ingest_token="secret")).validate_ingest_auth("Bearer secret")


def _config(
    *,
    ingest_token: str = "",
    max_correlation_nodes: int = 200,
) -> AgentLogAnalysisConfig:
    return AgentLogAnalysisConfig(
        host="0.0.0.0",
        port=8794,
        database_url="postgresql://example",
        db_schema="agent_log_analysis",
        ingest_token=ingest_token,
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
        max_correlation_nodes=max_correlation_nodes,
        max_aggregation_group_keys=3,
    )


def _assert_error_code(
    case: unittest.TestCase,
    expected: str,
    callback: Callable[[], object],
) -> None:
    try:
        callback()
    except ValidationError as err:
        case.assertEqual(err.error_code, expected)
        return
    case.fail("expected ValidationError")
