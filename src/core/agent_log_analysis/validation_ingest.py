"""Validation and normalization for ingest requests."""

from __future__ import annotations

from typing import Any

from core.agent_log_analysis.api_models import IngestEventRequest
from core.agent_log_analysis.config import AgentLogAnalysisConfig
from core.agent_log_analysis.validation_ingest_models import (
    BatchItemError,
    BatchValidationResult,
    ValidatedIngestEvent,
)
from core.agent_log_analysis.validation_ingest_parsers import (
    coerce_batch_request,
    coerce_event_request,
)
from core.agent_log_analysis.validation_ingest_records import normalize_raw_log
from core.agent_log_analysis.validation_ingest_shapes import validate_event_payload_shape
from core.agent_log_analysis.validation_ingest_support import (
    NormalizedEventContext,
    build_context,
    event_defaults,
    normalize_payload_parts,
)
from core.agent_log_analysis.validation_scalars import optional_text
from core.agent_log_analysis.validation_time import serialize_timestamp


class IngestValidator:
    """Validate and normalize ingest payloads."""

    def __init__(self, config: AgentLogAnalysisConfig) -> None:
        self._config = config

    def validate_event(self, payload: Any) -> ValidatedIngestEvent:
        """Validate one ingest event payload."""
        request = coerce_event_request(payload)
        return self._validate_request(request)

    def validate_batch(self, payload: Any) -> BatchValidationResult:
        """Validate batch payload and keep indexed errors."""
        batch = coerce_batch_request(payload)
        events: list[ValidatedIngestEvent] = []
        errors: list[BatchItemError] = []
        for index, item in enumerate(batch.events):
            self._append_batch_outcome(events, errors, index=index, request=item)
        return BatchValidationResult(events=events, errors=errors)

    def _append_batch_outcome(
        self,
        events: list[ValidatedIngestEvent],
        errors: list[BatchItemError],
        *,
        index: int,
        request: IngestEventRequest,
    ) -> None:
        try:
            events.append(self._validate_request(request, index=index))
        except Exception as err:
            errors.append(_to_batch_error(err, index=index))

    def _validate_request(
        self,
        request: IngestEventRequest,
        *,
        index: int | None = None,
    ) -> ValidatedIngestEvent:
        context = build_context(request)
        normalized_request = _build_normalized_request(
            request,
            config=self._config,
            context=context,
        )
        return ValidatedIngestEvent(
            request=normalized_request,
            occurred_at=context.occurred_at,
            event_type=context.event_type,
            index=index,
        )


def _build_normalized_request(
    request: IngestEventRequest,
    *,
    config: AgentLogAnalysisConfig,
    context: NormalizedEventContext,
) -> IngestEventRequest:
    parts = normalize_payload_parts(request, config=config)
    validate_event_payload_shape(
        context.event_type,
        inference=parts.inference,
        action=parts.action,
    )
    defaults = event_defaults(request, context=context)
    raw_logs = _normalize_raw_logs(
        request.raw_logs,
        config=config,
        defaults=defaults,
    )
    return IngestEventRequest(
        event_id=context.event_id,
        event_type=context.event_type.value,
        occurred_at=serialize_timestamp(context.occurred_at),
        agent_slug=context.agent_slug,
        run_id=optional_text(request.run_id),
        thread_id=optional_text(request.thread_id),
        correlation_id=optional_text(request.correlation_id),
        parent_event_id=optional_text(request.parent_event_id),
        labels=parts.labels,
        metadata=parts.metadata,
        raw_payload=parts.raw_payload,
        inference=parts.inference,
        action=parts.action,
        raw_logs=raw_logs,
    )


def _normalize_raw_logs(
    raw_logs: list[dict[str, Any]],
    *,
    config: AgentLogAnalysisConfig,
    defaults: dict[str, str | None],
) -> list[dict[str, Any]]:
    return [
        normalize_raw_log(raw_log, event_defaults=defaults, config=config) for raw_log in raw_logs
    ]


def _to_batch_error(err: Exception, *, index: int) -> BatchItemError:
    if hasattr(err, "error_code") and hasattr(err, "message"):
        return BatchItemError(
            index=index,
            error_code=err.error_code,
            message=err.message,
        )
    return BatchItemError(
        index=index,
        error_code="VALIDATION_ERROR",
        message=str(err),
    )
