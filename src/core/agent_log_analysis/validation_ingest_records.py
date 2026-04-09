"""Record-level normalization for ingest payloads."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from core.agent_log_analysis.config import AgentLogAnalysisConfig
from core.agent_log_analysis.errors import ValidationError
from core.agent_log_analysis.validation_ingest_enums import (
    parse_action_kind,
    parse_action_status,
    parse_inference_request_kind,
    parse_inference_status,
    parse_raw_log_level,
)
from core.agent_log_analysis.validation_ingest_payloads import normalize_optional_payload
from core.agent_log_analysis.validation_json import coerce_optional_mapping
from core.agent_log_analysis.validation_scalars import (
    bounded_text,
    optional_bounded_text,
    optional_text,
)
from core.agent_log_analysis.validation_time import parse_timestamp, serialize_timestamp

EnumParser = Callable[[Any], Any]


def normalize_inference(
    payload: dict[str, Any] | None,
    *,
    max_error_bytes: int,
) -> dict[str, Any] | None:
    """Validate and normalize inference payload."""
    if payload is None:
        return None
    result = _copy_optional_fields(
        payload,
        field_names=("model_name", "provider_name"),
    )
    _set_enum_value(
        result,
        key="request_kind",
        raw_value=payload.get("request_kind"),
        parser=parse_inference_request_kind,
    )
    _set_enum_value(
        result,
        key="status",
        raw_value=payload.get("status"),
        parser=parse_inference_status,
    )
    _append_int_field(result, payload, field_name="latency_ms")
    _append_int_field(result, payload, field_name="input_tokens")
    _append_int_field(result, payload, field_name="output_tokens")
    error_message = optional_bounded_text(
        payload.get("error_message"),
        field_name="inference.error_message",
        max_bytes=max_error_bytes,
    )
    if error_message is not None:
        result["error_message"] = error_message
    return result


def normalize_action(
    payload: dict[str, Any] | None,
    *,
    max_error_bytes: int,
) -> dict[str, Any] | None:
    """Validate and normalize action payload."""
    if payload is None:
        return None
    result = _copy_optional_fields(
        payload,
        field_names=("target_name", "target_agent_slug"),
    )
    _set_enum_value(
        result,
        key="action_kind",
        raw_value=payload.get("action_kind"),
        parser=parse_action_kind,
    )
    _set_enum_value(
        result,
        key="status",
        raw_value=payload.get("status"),
        parser=parse_action_status,
    )
    _append_int_field(result, payload, field_name="latency_ms")
    error_message = optional_bounded_text(
        payload.get("error_message"),
        field_name="action.error_message",
        max_bytes=max_error_bytes,
    )
    if error_message is not None:
        result["error_message"] = error_message
    return result


def normalize_raw_log(
    payload: dict[str, Any],
    *,
    event_defaults: dict[str, str | None],
    config: AgentLogAnalysisConfig,
) -> dict[str, Any]:
    """Normalize one raw log payload using event-level defaults."""
    raw_payload = coerce_optional_mapping(
        payload.get("raw_payload_json"),
        field_name="raw_logs[].raw_payload_json",
    )
    return {
        "event_id": optional_text(payload.get("event_id")) or event_defaults["event_id"],
        "occurred_at": serialize_timestamp(
            parse_timestamp(payload.get("occurred_at"), field_name="raw_logs[].occurred_at"),
        ),
        "agent_slug": optional_text(payload.get("agent_slug")) or event_defaults["agent_slug"],
        "run_id": optional_text(payload.get("run_id")) or event_defaults["run_id"],
        "thread_id": optional_text(payload.get("thread_id")) or event_defaults["thread_id"],
        "correlation_id": optional_text(payload.get("correlation_id"))
        or event_defaults["correlation_id"],
        "source": optional_text(payload.get("source")),
        "level": parse_raw_log_level(payload.get("level")).value,
        "raw_message": bounded_text(
            payload.get("raw_message"),
            field_name="raw_logs[].raw_message",
            max_bytes=config.max_raw_message_bytes,
        ),
        "raw_payload_json": normalize_optional_payload(
            raw_payload,
            field_name="raw_logs[].raw_payload_json",
            max_bytes=config.max_raw_payload_bytes,
        ),
    }


def _copy_optional_fields(
    payload: dict[str, Any],
    *,
    field_names: tuple[str, ...],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field_name in field_names:
        value = optional_text(payload.get(field_name))
        if value is not None:
            result[field_name] = value
    return result


def _set_enum_value(
    result: dict[str, Any],
    *,
    key: str,
    raw_value: Any,
    parser: EnumParser,
) -> None:
    if raw_value is None:
        return
    result[key] = parser(raw_value).value


def _append_int_field(
    result: dict[str, Any],
    payload: dict[str, Any],
    *,
    field_name: str,
) -> None:
    raw_value = payload.get(field_name)
    if raw_value is None:
        return
    if isinstance(raw_value, bool) or not isinstance(raw_value, int) or raw_value < 0:
        raise ValidationError(
            "VALIDATION_ERROR",
            f"{field_name} must be a non-negative integer",
        )
    result[field_name] = raw_value
