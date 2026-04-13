"""Internal configuration builders for the canonical SGR backend."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

from core.orchestra_agents.backends.sgr import support as _support
from core.orchestra_agents.backends.sgr.llm import routing as _routing
from core.orchestra_agents.backends.sgr.normalization import values as _values


class _BoolNormalizer(Protocol):
    def __call__(self, normalized_value: object, *, default: bool = False) -> bool: ...


@dataclass(frozen=True)
class SGRLLMConfig:
    """LLM configuration for the SGR agent backend."""

    route_policy: str
    model: str | None
    timeout_seconds: float | None
    temperature: float | None
    max_tokens: int | None
    text_verbosity: str | None
    reasoning_effort: str | None
    reasoning_summary: str | None


def build_llm_config(raw: dict[str, Any]) -> SGRLLMConfig:
    """Build LLM config from raw config dict and environment."""
    model = _resolved_model(raw)
    route_policy = _resolved_route_policy(raw, model)
    return SGRLLMConfig(
        route_policy=route_policy,
        model=model,
        timeout_seconds=_values.normalize_optional_float(
            raw.get("timeout_seconds") or os.getenv("LLM_CLIENT_TIMEOUT_SECONDS")
        ),
        temperature=_values.normalize_optional_float(raw.get("temperature")),
        max_tokens=_values.normalize_optional_int(raw.get("max_tokens")),
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


def build_settings(
    raw: dict[str, Any],
    *,
    normalize_bool: _BoolNormalizer,
) -> _support.SGRRuntimeSettings:
    """Build runtime settings from raw config dict and environment."""
    return _support.SGRRuntimeSettings(
        react_to_inactive=normalize_bool(raw.get("react_to_inactive"), default=True),
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


def _resolved_model(raw: dict[str, Any]) -> str | None:
    env_model = _support.normalize_optional_str(os.getenv("LLM_CLIENT_MODEL"))
    configured_model = _support.normalize_optional_str(raw.get("model"))
    return env_model or configured_model


def _resolved_route_policy(raw: dict[str, Any], model: str | None) -> str:
    env_route_policy = _support.normalize_optional_str(os.getenv("LLM_CLIENT_ROUTE_POLICY"))
    configured_route_policy = _support.normalize_optional_str(raw.get("route_policy"))
    fallback_route_policy = configured_route_policy or "minimax_only"
    return env_route_policy or _routing.infer_route_policy(model, fallback_route_policy)
