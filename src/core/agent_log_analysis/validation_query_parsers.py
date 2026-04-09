"""Typed request coercion for analytical validators."""

from __future__ import annotations

from typing import Any

from core.agent_log_analysis.api_query_models import (
    AgentAggregateRequest,
    AgentCorrelationRequest,
    AgentEventQueryRequest,
    AgentRawLogQueryRequest,
    AgentTimelineRequest,
)
from core.agent_log_analysis.validation_json import coerce_mapping
from core.agent_log_analysis.validation_scalars import optional_int, optional_text


def coerce_event_request(payload: Any) -> AgentEventQueryRequest:
    """Coerce event-query payload into DTO."""
    if isinstance(payload, AgentEventQueryRequest):
        return payload
    mapping = coerce_mapping(payload, field_name="query payload")
    return AgentEventQueryRequest(
        agent_slug=str(mapping.get("agent_slug") or ""),
        window_start=optional_text(mapping.get("window_start")),
        window_end=optional_text(mapping.get("window_end")),
        run_id=optional_text(mapping.get("run_id")),
        thread_id=optional_text(mapping.get("thread_id")),
        correlation_id=optional_text(mapping.get("correlation_id")),
        event_type=optional_text(mapping.get("event_type")),
        status=optional_text(mapping.get("status")),
        request_kind=optional_text(mapping.get("request_kind")),
        action_kind=optional_text(mapping.get("action_kind")),
        target_name=optional_text(mapping.get("target_name")),
        target_agent_slug=optional_text(mapping.get("target_agent_slug")),
        provider_name=optional_text(mapping.get("provider_name")),
        model_name=optional_text(mapping.get("model_name")),
        labels=_coerce_string_mapping(mapping.get("labels", {}), field_name="labels"),
        cursor=optional_text(mapping.get("cursor")),
        limit=optional_int(mapping.get("limit"), field_name="limit"),
    )


def coerce_timeline_request(payload: Any) -> AgentTimelineRequest:
    """Coerce timeline-query payload into DTO."""
    if isinstance(payload, AgentTimelineRequest):
        return payload
    mapping = coerce_mapping(payload, field_name="query payload")
    return AgentTimelineRequest(
        agent_slug=str(mapping.get("agent_slug") or ""),
        window_start=optional_text(mapping.get("window_start")),
        window_end=optional_text(mapping.get("window_end")),
        run_id=optional_text(mapping.get("run_id")),
        thread_id=optional_text(mapping.get("thread_id")),
        cursor=optional_text(mapping.get("cursor")),
        limit=optional_int(mapping.get("limit"), field_name="limit"),
    )


def coerce_correlation_request(payload: Any) -> AgentCorrelationRequest:
    """Coerce correlation-query payload into DTO."""
    if isinstance(payload, AgentCorrelationRequest):
        return payload
    mapping = coerce_mapping(payload, field_name="query payload")
    return AgentCorrelationRequest(
        agent_slug=str(mapping.get("agent_slug") or ""),
        correlation_id=str(mapping.get("correlation_id") or ""),
        run_id=optional_text(mapping.get("run_id")),
        thread_id=optional_text(mapping.get("thread_id")),
    )


def coerce_aggregate_request(payload: Any) -> AgentAggregateRequest:
    """Coerce aggregate-query payload into DTO."""
    if isinstance(payload, AgentAggregateRequest):
        return payload
    mapping = coerce_mapping(payload, field_name="query payload")
    return AgentAggregateRequest(
        agent_slug=str(mapping.get("agent_slug") or ""),
        window_start=str(mapping.get("window_start") or ""),
        window_end=str(mapping.get("window_end") or ""),
        group_by=_coerce_string_list(mapping.get("group_by", []), field_name="group_by"),
        metrics=_coerce_string_list(mapping.get("metrics", []), field_name="metrics"),
    )


def coerce_raw_log_request(payload: Any) -> AgentRawLogQueryRequest:
    """Coerce raw-log query payload into DTO."""
    if isinstance(payload, AgentRawLogQueryRequest):
        return payload
    mapping = coerce_mapping(payload, field_name="query payload")
    return AgentRawLogQueryRequest(
        agent_slug=str(mapping.get("agent_slug") or ""),
        window_start=optional_text(mapping.get("window_start")),
        window_end=optional_text(mapping.get("window_end")),
        run_id=optional_text(mapping.get("run_id")),
        thread_id=optional_text(mapping.get("thread_id")),
        correlation_id=optional_text(mapping.get("correlation_id")),
        event_id=optional_text(mapping.get("event_id")),
        level=optional_text(mapping.get("level")),
        source=optional_text(mapping.get("source")),
        cursor=optional_text(mapping.get("cursor")),
        limit=optional_int(mapping.get("limit"), field_name="limit"),
    )


def _coerce_string_mapping(payload: Any, *, field_name: str) -> dict[str, str]:
    if payload is None:
        return {}
    mapping = coerce_mapping(payload, field_name=field_name)
    return {
        str(key).strip(): str(value).strip()
        for key, value in mapping.items()
        if str(key).strip() and str(value).strip()
    }


def _coerce_string_list(payload: Any, *, field_name: str) -> list[str]:
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise TypeError(f"{field_name} must be a list")
    return [str(item).strip() for item in payload if str(item).strip()]
