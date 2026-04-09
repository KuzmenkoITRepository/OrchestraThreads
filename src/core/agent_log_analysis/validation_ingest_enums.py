"""Enum parsing helpers for ingest validation."""

from __future__ import annotations

from enum import Enum
from typing import Any, TypeVar

from core.agent_log_analysis.errors import ValidationError
from core.agent_log_analysis.event_action import ActionKind, ActionStatus
from core.agent_log_analysis.event_envelope import EventType
from core.agent_log_analysis.event_inference import (
    InferenceRequestKind,
    InferenceStatus,
)
from core.agent_log_analysis.raw_log_models import RawLogLevel
from core.agent_log_analysis.validation_scalars import required_text

EnumT = TypeVar("EnumT", bound=Enum)


def parse_event_type(value: Any) -> EventType:
    """Parse the canonical event type."""
    return _parse_enum(
        value,
        field_name="event_type",
        enum_type=EventType,
        message="event_type is invalid",
    )


def parse_inference_request_kind(value: Any) -> InferenceRequestKind:
    """Parse inference request kind enum."""
    return _parse_enum(
        value,
        field_name="inference.request_kind",
        enum_type=InferenceRequestKind,
        message="inference.request_kind is invalid",
    )


def parse_inference_status(value: Any) -> InferenceStatus:
    """Parse inference status enum."""
    return _parse_enum(
        value,
        field_name="inference.status",
        enum_type=InferenceStatus,
        message="inference.status is invalid",
    )


def parse_action_kind(value: Any) -> ActionKind:
    """Parse action kind enum."""
    return _parse_enum(
        value,
        field_name="action.action_kind",
        enum_type=ActionKind,
        message="action.action_kind is invalid",
    )


def parse_action_status(value: Any) -> ActionStatus:
    """Parse action status enum."""
    return _parse_enum(
        value,
        field_name="action.status",
        enum_type=ActionStatus,
        message="action.status is invalid",
    )


def parse_raw_log_level(value: Any) -> RawLogLevel:
    """Parse raw log level enum."""
    return _parse_enum(
        value,
        field_name="raw_logs[].level",
        enum_type=RawLogLevel,
        message="raw_logs[].level is invalid",
    )


def _parse_enum(
    value: Any,
    *,
    field_name: str,
    enum_type: type[EnumT],
    message: str,
) -> EnumT:
    raw_value = required_text(value, field_name=field_name)
    try:
        return enum_type(raw_value)
    except ValueError as err:
        raise ValidationError("VALIDATION_ERROR", message) from err
