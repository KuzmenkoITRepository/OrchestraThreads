from __future__ import annotations

import hashlib
import importlib
import logging
from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

TRACE_NAME_RESPONSES = "llm_proxy.responses"
TRACE_NAME_CHAT = "llm_proxy.chat_completions"
GENERATION_NAME_CODEX = "llm_proxy.codex_attempt"
GENERATION_NAME_FALLBACK = "llm_proxy.fallback_attempt"


def truncate_text(value: Any, *, limit: int = 300) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[: limit - 3] + "..."


def _ascii_limited(value: Any, *, limit: int = 200) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.encode("ascii", "ignore").decode("ascii").strip()
    if not normalized:
        return None
    if len(normalized) > limit:
        normalized = normalized[:limit]
    return normalized


def build_group_key(agent_slug: str | None, context_id: str | None) -> str | None:
    normalized_agent = _ascii_limited(agent_slug, limit=80)
    normalized_context = _ascii_limited(context_id, limit=96)
    if not normalized_agent or not normalized_context:
        return None
    raw = f"{normalized_agent}:{normalized_context}"
    if len(raw) <= 200:
        return raw
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    prefix = normalized_agent[: max(1, 200 - len(digest) - 1)]
    return f"{prefix}:{digest}"


def _metadata_value(value: Any) -> str | None:
    normalized = _ascii_limited(value, limit=200)
    if normalized is None:
        return None
    return normalized


def compact_metadata(payload: Mapping[str, Any] | None) -> dict[str, str]:
    if not payload:
        return {}
    normalized: dict[str, str] = {}
    for key, value in payload.items():
        normalized_key = _ascii_limited(key, limit=120)
        normalized_value = _metadata_value(value)
        if not normalized_key or normalized_value is None:
            continue
        normalized[normalized_key] = normalized_value
    return normalized


def request_trace_name(request_kind: str | None) -> str:
    normalized = str(request_kind or "").strip().lower()
    if normalized == "chat_completions":
        return TRACE_NAME_CHAT
    return TRACE_NAME_RESPONSES


def summarize_input_items(
    input_items: Sequence[Mapping[str, Any]] | None, *, preview_limit: int = 3
) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for item in list(input_items or [])[:preview_limit]:
        if not isinstance(item, Mapping):
            continue
        row: dict[str, Any] = {}
        role = str(item.get("role") or "").strip()
        if role:
            row["role"] = role
        content = item.get("content")
        if isinstance(content, list):
            parts: list[str] = []
            types: list[str] = []
            for part in content[:5]:
                if not isinstance(part, Mapping):
                    continue
                part_type = str(part.get("type") or "").strip()
                if part_type:
                    types.append(part_type)
                text_value = part.get("text")
                if isinstance(text_value, str) and text_value.strip():
                    parts.append(truncate_text(text_value, limit=160))
            if types:
                row["content_types"] = types
            if parts:
                row["text_preview"] = "\n".join(parts)
        if row:
            summary.append(row)
    return summary


def summarize_tools(tools: Sequence[Mapping[str, Any]] | None) -> list[str]:
    names: list[str] = []
    for item in list(tools or [])[:10]:
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("name") or "").strip()
        if name:
            names.append(name)
    return names


def summarize_request_input(
    *,
    instructions: str,
    input_items: Sequence[Mapping[str, Any]] | None,
    tools: Sequence[Mapping[str, Any]] | None,
    model: str | None,
    route_policy: str,
    request_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    stream_value = request_metadata.get("stream") if isinstance(request_metadata, Mapping) else None
    payload: dict[str, Any] = {
        "instructions_preview": truncate_text(instructions, limit=300),
        "input_item_count": len(list(input_items or [])),
        "inputs_preview": summarize_input_items(input_items),
        "tool_names": summarize_tools(tools),
        "requested_model": str(model or "").strip() or None,
        "route_policy": str(route_policy or "").strip() or None,
        "stream": bool(stream_value) if stream_value is not None else None,
    }
    return {key: value for key, value in payload.items() if value not in (None, [], "")}


def summarize_codex_response(response: Any) -> dict[str, Any]:
    items_payload: list[dict[str, Any]] = []
    for item in list(getattr(response, "items", []) or [])[:5]:
        item_type = str(getattr(item, "type", "") or "").strip()
        if item_type == "assistant_text":
            items_payload.append(
                {
                    "type": item_type,
                    "text_preview": truncate_text(getattr(item, "text", ""), limit=300),
                }
            )
            continue
        if item_type == "tool_call":
            items_payload.append(
                {
                    "type": item_type,
                    "name": str(getattr(item, "name", "") or "").strip() or None,
                }
            )
            continue
        items_payload.append({"type": item_type or "unknown"})
    payload = {
        "model": str(getattr(response, "model", "") or "").strip() or None,
        "stop_reason": str(getattr(response, "stop_reason", "") or "").strip() or None,
        "usage": normalize_usage(getattr(response, "usage", None)),
        "items": items_payload,
    }
    return {key: value for key, value in payload.items() if value not in (None, [], "")}


def summarize_openai_response(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    preview = ""
    choices = payload.get("choices")
    if isinstance(choices, list):
        for choice in choices:
            if not isinstance(choice, Mapping):
                continue
            message = choice.get("message")
            if isinstance(message, Mapping):
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    preview = truncate_text(content, limit=300)
                    break
    result = {
        "model": str(payload.get("model") or "").strip() or None,
        "content_preview": preview or None,
        "usage": normalize_usage(payload.get("usage")),
    }
    return {key: value for key, value in result.items() if value not in (None, "", [])}


def normalize_usage(payload: Any) -> dict[str, int] | None:
    if not isinstance(payload, Mapping):
        return None
    normalized: dict[str, int] = {}
    for key, value in payload.items():
        if value is None:
            continue
        try:
            normalized[str(key)] = int(value)
        except (TypeError, ValueError):
            continue
    return normalized or None


def model_parameters(
    *,
    temperature: float | None = None,
    text_verbosity: str | None = None,
    reasoning_effort: str | None = None,
    reasoning_summary: str | None = None,
) -> dict[str, Any] | None:
    payload: dict[str, Any] = {}
    if temperature is not None:
        payload["temperature"] = float(temperature)
    if str(text_verbosity or "").strip():
        payload["text_verbosity"] = str(text_verbosity).strip()
    if str(reasoning_effort or "").strip():
        payload["reasoning_effort"] = str(reasoning_effort).strip()
    if str(reasoning_summary or "").strip():
        payload["reasoning_summary"] = str(reasoning_summary).strip()
    return payload or None


class _NullObservation:
    def update(self, **_: Any) -> None:
        return None


class RequestTrace(AbstractContextManager["RequestTrace"]):
    def generation(
        self,
        *,
        name: str,
        model: str | None = None,
        input_payload: Any = None,
        metadata: Mapping[str, Any] | None = None,
        model_parameters_payload: Mapping[str, Any] | None = None,
    ) -> AbstractContextManager[Any]:
        raise NotImplementedError

    def mark_success(
        self, *, output: Any = None, metadata: Mapping[str, Any] | None = None
    ) -> None:
        raise NotImplementedError

    def mark_error(
        self,
        *,
        error: Exception | str,
        output: Any = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        raise NotImplementedError


class NullRequestTrace(RequestTrace):
    def __enter__(self) -> NullRequestTrace:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False

    def generation(
        self,
        *,
        name: str,
        model: str | None = None,
        input_payload: Any = None,
        metadata: Mapping[str, Any] | None = None,
        model_parameters_payload: Mapping[str, Any] | None = None,
    ) -> AbstractContextManager[Any]:
        del name, model, input_payload, metadata, model_parameters_payload
        return nullcontext(_NullObservation())

    def mark_success(
        self, *, output: Any = None, metadata: Mapping[str, Any] | None = None
    ) -> None:
        del output, metadata

    def mark_error(
        self,
        *,
        error: Exception | str,
        output: Any = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        del error, output, metadata


@dataclass(frozen=True)
class TelemetrySettings:
    enabled: bool
    public_key: str | None = None
    secret_key: str | None = None
    base_url: str | None = None
    environment: str | None = None
    release: str | None = None


class LangfuseRequestTrace(RequestTrace):
    def __init__(
        self,
        *,
        client: Any,
        trace_name: str,
        session_id: str | None,
        metadata: Mapping[str, Any] | None,
        input_payload: Any,
        version: str | None,
        tags: Sequence[str] | None,
    ) -> None:
        self._client = client
        self._trace_name = trace_name
        self._session_id = session_id
        self._metadata = compact_metadata(metadata)
        self._input_payload = input_payload
        self._version = _ascii_limited(version, limit=120)
        self._tags = [
            item for item in (_ascii_limited(tag, limit=120) for tag in list(tags or [])) if item
        ]
        self._trace: Any | None = None
        self._finalized = False

    def __enter__(self) -> LangfuseRequestTrace:
        self._trace = self._client.trace(
            name=self._trace_name,
            session_id=self._session_id,
            input=self._input_payload,
            metadata=self._metadata or None,
            version=self._version,
            tags=self._tags or None,
        )
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        if exc is not None and not self._finalized:
            self.mark_error(error=exc)
        if self._trace is not None:
            self._client.flush()
        return False

    def generation(
        self,
        *,
        name: str,
        model: str | None = None,
        input_payload: Any = None,
        metadata: Mapping[str, Any] | None = None,
        model_parameters_payload: Mapping[str, Any] | None = None,
    ) -> AbstractContextManager[Any]:
        if self._trace is None:
            return nullcontext(_NullObservation())

        generation = self._trace.generation(
            name=name,
            model=model,
            input=input_payload,
            metadata=dict(metadata or {}) or None,
            model_parameters=dict(model_parameters_payload or {}) or None,
        )
        return nullcontext(generation)

    def mark_success(
        self, *, output: Any = None, metadata: Mapping[str, Any] | None = None
    ) -> None:
        if self._trace is None:
            return
        self._finalized = True
        self._trace.update(
            output=output,
            metadata=compact_metadata(metadata) or None,
        )

    def mark_error(
        self,
        *,
        error: Exception | str,
        output: Any = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        if self._trace is None:
            return
        self._finalized = True
        self._trace.update(
            output=output or {"error": truncate_text(error, limit=300)},
            metadata=compact_metadata(metadata) or None,
        )


class LangfuseTelemetry:
    def __init__(self, settings: TelemetrySettings | None = None) -> None:
        self.settings = settings or TelemetrySettings(enabled=False)
        self._client: Any | None = None
        self._client_error: str | None = None
        if self.settings.enabled:
            self._client = self._build_client()

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def _build_client(self) -> Any | None:
        if not self.settings.public_key or not self.settings.secret_key:
            logger.warning(
                "Langfuse tracing enabled but credentials are incomplete; tracing is disabled."
            )
            return None
        try:
            langfuse_module = importlib.import_module("langfuse")
            client_type = langfuse_module.Langfuse

            kwargs = {
                "public_key": self.settings.public_key,
                "secret_key": self.settings.secret_key,
            }
            if self.settings.base_url:
                kwargs["host"] = self.settings.base_url
            if self.settings.environment:
                kwargs["environment"] = self.settings.environment
            if self.settings.release:
                kwargs["release"] = self.settings.release

            return client_type(**kwargs)
        except Exception as exc:
            self._client_error = str(exc)
            logger.warning("Failed to initialize Langfuse client: %s", exc)
            return None

    def start_request(
        self,
        *,
        request_kind: str,
        agent_slug: str | None,
        context_id: str | None,
        metadata: Mapping[str, Any] | None,
        input_payload: Any,
        tags: Sequence[str] | None = None,
    ) -> RequestTrace:
        if self._client is None:
            return NullRequestTrace()
        return LangfuseRequestTrace(
            client=self._client,
            trace_name=request_trace_name(request_kind),
            session_id=build_group_key(agent_slug, context_id),
            metadata=metadata,
            input_payload=input_payload,
            version=self.settings.release,
            tags=tags,
        )

    def flush(self) -> None:
        if self._client is None:
            return
        try:
            self._client.flush()
        except Exception as exc:
            logger.warning("Langfuse flush failed: %s", exc)

    def shutdown(self) -> None:
        if self._client is None:
            return
        try:
            self._client.shutdown()
        except Exception as exc:
            logger.warning("Langfuse shutdown failed: %s", exc)
