"""Event-shape validation for ingest payloads."""

from __future__ import annotations

from typing import Any

from core.agent_log_analysis.errors import ValidationError
from core.agent_log_analysis.event_envelope import EventType


def validate_event_payload_shape(
    event_type: EventType,
    *,
    inference: dict[str, Any] | None,
    action: dict[str, Any] | None,
) -> None:
    """Validate mutual exclusivity between inference and action payloads."""
    if event_type is EventType.inference_event:
        _validate_inference_shape(inference=inference, action=action)
        return
    _validate_action_shape(inference=inference, action=action)


def _validate_inference_shape(
    *,
    inference: dict[str, Any] | None,
    action: dict[str, Any] | None,
) -> None:
    if inference is None:
        raise ValidationError(
            "VALIDATION_ERROR",
            "inference payload is required for inference_event",
        )
    if action is not None:
        raise ValidationError(
            "VALIDATION_ERROR",
            "action payload is not allowed for inference_event",
        )


def _validate_action_shape(
    *,
    inference: dict[str, Any] | None,
    action: dict[str, Any] | None,
) -> None:
    if action is None:
        raise ValidationError(
            "VALIDATION_ERROR",
            "action payload is required for action_event",
        )
    if inference is not None:
        raise ValidationError(
            "VALIDATION_ERROR",
            "inference payload is not allowed for action_event",
        )
