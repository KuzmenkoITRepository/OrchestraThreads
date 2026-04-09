"""Inference-specific normalized fields for agent telemetry."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class InferenceRequestKind(StrEnum):
    """Kind of inference request."""

    chat = "chat"
    completion = "completion"
    tool_selection = "tool-selection"
    other = "other"


class InferenceStatus(StrEnum):
    """Status of an inference request."""

    success = "success"
    error = "error"
    timeout = "timeout"
    cancelled = "cancelled"


@dataclass(frozen=True)
class InferencePayload:
    """Normalized inference-specific fields."""

    model_name: str | None = None
    provider_name: str | None = None
    request_kind: InferenceRequestKind | None = None
    status: InferenceStatus | None = None
    latency_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    error_message: str | None = None
