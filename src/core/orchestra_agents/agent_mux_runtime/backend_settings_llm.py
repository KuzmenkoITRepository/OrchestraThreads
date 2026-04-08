from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

CODEX_ONLY_POLICY = "codex_only"
DEFAULT_MODEL = "cx/gpt-5.1-codex-mini"


@dataclass(frozen=True)
class LLMClientConfig:
    route_policy: str
    model: str | None
    timeout_seconds: float | None
    reasoning_effort: str | None
    reasoning_summary: str | None
    text_verbosity: str | None


def optional_str(raw_value: Any) -> str | None:
    if raw_value is None:
        return None
    text = str(raw_value).strip()
    return text or None


def optional_float(raw_value: Any) -> float | None:
    if raw_value is None:
        return None
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return None


def resolve_llm_client_config(raw_config: dict[str, Any]) -> LLMClientConfig:
    return LLMClientConfig(
        route_policy=str(raw_config.get("route_policy") or CODEX_ONLY_POLICY).strip()
        or CODEX_ONLY_POLICY,
        model=optional_str(raw_config.get("model")),
        timeout_seconds=optional_float(raw_config.get("timeout_seconds")),
        reasoning_effort=optional_str(raw_config.get("reasoning_effort")),
        reasoning_summary=optional_str(raw_config.get("reasoning_summary")),
        text_verbosity=optional_str(raw_config.get("text_verbosity")),
    )


def llm_runtime_settings(
    raw_config: dict[str, Any],
    *,
    llm_config: LLMClientConfig,
    llm_route_policy: str | None,
    llm_model: str | None,
) -> dict[str, Any]:
    return {
        "omniroute_url": str(
            raw_config.get("omniroute_url") or "http://orchestra-omniroute:20128"
        ).rstrip("/"),
        "omniroute_api_key": str(
            raw_config.get("omniroute_api_key") or os.getenv("OMNIROUTE_API_KEY") or ""
        ).strip(),
        "llm_route_policy": str(
            llm_route_policy or llm_config.route_policy or CODEX_ONLY_POLICY
        ).strip()
        or CODEX_ONLY_POLICY,
        "default_model": str(llm_model or llm_config.model or DEFAULT_MODEL).strip()
        or DEFAULT_MODEL,
    }
