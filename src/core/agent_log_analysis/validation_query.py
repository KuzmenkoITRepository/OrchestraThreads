"""Validation and bounds enforcement for analytical queries."""

from __future__ import annotations

from importlib import import_module
from typing import Protocol, cast

from core.agent_log_analysis import config as log_config
from core.agent_log_analysis import errors
from core.agent_log_analysis import store_aggregates as aggregate_store
from core.agent_log_analysis import store_correlation as correlation_store
from core.agent_log_analysis import store_query_sql as query_store
from core.agent_log_analysis import validation_query_builders as query_builders
from core.agent_log_analysis import validation_query_models as query_models
from core.agent_log_analysis import validation_query_parsers as query_parsers
from core.agent_log_analysis.api_query_models import AgentRawLogQueryRequest


class _RawLogQueryBuilder(Protocol):
    def __call__(
        self,
        request: AgentRawLogQueryRequest,
        *,
        config: log_config.AgentLogAnalysisConfig,
    ) -> query_models.ValidatedRawLogQuery: ...


class QueryValidator:
    """Validate analytical requests and ingest auth policy."""

    def __init__(self, config: log_config.AgentLogAnalysisConfig) -> None:
        self._config = config

    def validate_event_query(self, payload: object) -> query_store.EventQueryParams:
        """Validate event list query."""
        request = query_parsers.coerce_event_request(payload)
        return query_builders.build_event_query_params(request, config=self._config)

    def validate_timeline_query(self, payload: object) -> query_store.EventQueryParams:
        """Validate timeline query."""
        request = query_parsers.coerce_timeline_request(payload)
        return query_builders.build_timeline_query_params(request, config=self._config)

    def validate_correlation_query(
        self,
        payload: object,
    ) -> correlation_store.CorrelationQueryParams:
        """Validate correlation-chain query."""
        request = query_parsers.coerce_correlation_request(payload)
        return query_builders.build_correlation_query_params(request, config=self._config)

    def validate_aggregate_query(
        self,
        payload: object,
    ) -> aggregate_store.AggregateQueryParams:
        """Validate aggregation query."""
        request = query_parsers.coerce_aggregate_request(payload)
        return query_builders.build_aggregate_query_params(request, config=self._config)

    def validate_raw_log_query(self, payload: object) -> query_models.ValidatedRawLogQuery:
        """Validate raw-log query."""
        request = query_parsers.coerce_raw_log_request(payload)
        return _load_raw_log_query_builder()(
            request,
            config=self._config,
        )

    def validate_ingest_auth(self, authorization: str | None) -> None:
        """Validate optional bearer auth for HTTP ingest."""
        token = self._config.ingest_token
        if not token:
            return
        _validate_authorization_header(authorization, token=token)


def _validate_authorization_header(
    authorization: str | None,
    *,
    token: str,
) -> None:
    if authorization is None or not authorization.strip():
        raise errors.ValidationError("AUTH_REQUIRED", "Authorization header is required")
    scheme, _, supplied = authorization.strip().partition(" ")
    if scheme == "Bearer" and supplied == token:
        return
    raise errors.ValidationError("AUTH_INVALID", "Authorization header is invalid")


def _load_raw_log_query_builder() -> _RawLogQueryBuilder:
    module = import_module("core.agent_log_analysis.validation_query_raw_log_builders")
    return cast(_RawLogQueryBuilder, module.build_raw_log_query)
