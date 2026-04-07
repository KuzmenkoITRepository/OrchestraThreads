"""SGR runtime configuration construction."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from agents.sgr.agent_runtime import support as _support
from agents.sgr.agent_runtime import value_normalization as _value_norm
from core.orchestra_agents import agent_mux_runtime as _mux_rt


@dataclass(frozen=True)
class SGRLLMConfig:
    route_policy: str
    model: str | None
    timeout_seconds: float | None
    temperature: float | None
    max_tokens: int | None
    text_verbosity: str | None
    reasoning_effort: str | None
    reasoning_summary: str | None


def build_llm_config(raw: dict[str, Any]) -> SGRLLMConfig:
    return SGRLLMConfig(
        route_policy=str(raw.get("route_policy") or "minimax_only").strip() or "minimax_only",
        model=_support.normalize_optional_str(raw.get("model") or os.getenv("LLM_CLIENT_MODEL")),
        timeout_seconds=_value_norm.normalize_optional_float(
            raw.get("timeout_seconds") or os.getenv("LLM_CLIENT_TIMEOUT_SECONDS")
        ),
        temperature=_value_norm.normalize_optional_float(raw.get("temperature")),
        max_tokens=_value_norm.normalize_optional_int(raw.get("max_tokens")),
        text_verbosity=_support.normalize_optional_str(
            raw.get("text_verbosity") or os.getenv("LLM_CLIENT_TEXT_VERBOSITY")
        ),
        reasoning_effort=_support.normalize_optional_str(
            raw.get("reasoning_effort") or os.getenv("LLM_CLIENT_REASONING_EFFORT")
        ),
        reasoning_summary=_support.normalize_optional_str(
            raw.get("reasoning_summary") or os.getenv("LLM_CLIENT_REASONING_SUMMARY")
        ),
    )


def build_settings(raw: dict[str, Any]) -> _support.SGRRuntimeSettings:
    """Build SGRRuntimeSettings from raw config dict and environment."""
    threads_url_raw = raw.get("threads_url")
    if threads_url_raw is None:
        threads_url_raw = os.getenv("ORCHESTRA_THREADS_URL")
    endpoint_raw = raw.get("http_endpoint") or os.getenv("ORCHESTRA_AGENT_HTTP_ENDPOINT") or ""
    settings = _support.SGRRuntimeSettings(
        threads_url=_normalized_threads_url(threads_url_raw),
        http_endpoint=str(endpoint_raw).rstrip("/"),
        heartbeat_interval_seconds=_heartbeat_interval(raw),
        guide_view=_guide_view(raw),
        react_to_inactive=_mux_rt.normalize_bool(raw.get("react_to_inactive"), default=True),
        max_reasoning_steps=_support.normalize_int(
            os.getenv("SGR_MAX_REASONING_STEPS") or raw.get("max_reasoning_steps"),
            default=8,
            minimum=1,
        ),
        max_direct_text_retries=_support.normalize_int(
            os.getenv("SGR_MAX_DIRECT_TEXT_RETRIES") or raw.get("max_direct_text_retries"),
            default=2,
            minimum=0,
        ),
    )
    _validate_settings(settings)
    return settings


def _heartbeat_interval(raw: dict[str, Any]) -> float:
    return max(
        2.0,
        _mux_rt.normalize_float(
            os.getenv("SGR_HEARTBEAT_INTERVAL_SECONDS") or raw.get("heartbeat_interval_seconds"),
            default=10.0,
        ),
    )


def _guide_view(raw: dict[str, Any]) -> str:
    raw_view = str(raw.get("guide_view") or "compact").strip().lower()
    return raw_view or "compact"


def _normalized_threads_url(threads_url_raw: Any) -> str | None:
    if isinstance(threads_url_raw, str):
        return _support.normalize_optional_str(threads_url_raw.rstrip("/"))
    return _support.normalize_optional_str(threads_url_raw)


def _validate_settings(settings: _support.SGRRuntimeSettings) -> None:
    _support.validate_threads_url(settings.threads_url)
    _support.validate_http_endpoint(settings.http_endpoint)
    _support.validate_reasoning_steps(settings.max_reasoning_steps)
