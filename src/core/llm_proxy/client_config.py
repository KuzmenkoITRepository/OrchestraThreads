from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping


ROUTE_POLICY_MANAGED_AUTO = "managed_auto"
ROUTE_POLICY_CODEX_ONLY = "codex_only"
ROUTE_POLICY_MINIMAX_ONLY = "minimax_only"
ROUTE_POLICY_LEGACY_OPENAI = "legacy_openai"

DEFAULT_LLM_PROXY_URL = "http://llm-proxy:8787"
DEFAULT_LLM_PROXY_API_KEY = "llm-proxy"
DEFAULT_LLM_PROXY_MODEL = "gpt-5.4"
LLM_PROXY_TRACE_AGENT_HEADER = "X-Orchestra-Agent-Slug"
LLM_PROXY_TRACE_CONTEXT_HEADER = "X-Orchestra-Context-Id"
LLM_PROXY_TRACE_SESSION_HEADER = "X-Orchestra-Langfuse-Session-Id"
LLM_PROXY_TRACE_USER_HEADER = "X-Orchestra-Langfuse-User-Id"


@dataclass(frozen=True)
class LLMClientConfig:
    route_policy: str = ROUTE_POLICY_MANAGED_AUTO
    model: str | None = None
    timeout_seconds: int | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    text_verbosity: str | None = None
    reasoning_effort: str | None = None
    reasoning_summary: str | None = None


def parse_csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    parts = [part.strip() for part in value.split(",")]
    return tuple(part for part in parts if part)


def normalize_route_policy(value: str | None, *, default: str = ROUTE_POLICY_MANAGED_AUTO) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    if not normalized:
        return default
    if normalized in {"managed", "auto", "default", "managed_auto", "codex_proxy", "proxy"}:
        return ROUTE_POLICY_MANAGED_AUTO
    if normalized in {"codex", "codex_only"}:
        return ROUTE_POLICY_CODEX_ONLY
    if normalized in {"minimax", "minimax_only", "fallback", "fallback_only"}:
        return ROUTE_POLICY_MINIMAX_ONLY
    if normalized in {"legacy", "legacy_openai", "openai", "openai_compat", "openai_compatible"}:
        return ROUTE_POLICY_LEGACY_OPENAI
    return default


def route_policy_path_prefix(route_policy: str) -> str:
    normalized = normalize_route_policy(route_policy)
    if normalized == ROUTE_POLICY_CODEX_ONLY:
        return "/codex"
    if normalized == ROUTE_POLICY_MINIMAX_ONLY:
        return "/minimax"
    return ""


def resolve_llm_proxy_url() -> str:
    return (
        os.getenv("LLM_PROXY_URL")
        or os.getenv("ORCHESTRA_CORE_CODEX_PROXY_URL")
        or DEFAULT_LLM_PROXY_URL
    ).strip()


def resolve_llm_proxy_api_key() -> str:
    return (
        os.getenv("LLM_PROXY_API_KEY")
        or os.getenv("ORCHESTRA_CORE_CODEX_PROXY_API_KEY")
        or DEFAULT_LLM_PROXY_API_KEY
    ).strip()


def llm_proxy_enabled() -> bool:
    value = os.getenv("LLM_PROXY_ENABLED")
    if value is None:
        return True
    return value.strip().lower() in {"1", "true", "yes", "on"}


def default_route_policy() -> str:
    return normalize_route_policy(
        os.getenv("LLM_PROXY_DEFAULT_ROUTE_POLICY") or ROUTE_POLICY_MANAGED_AUTO,
    )


def build_llm_proxy_openai_base_url(route_policy: str, *, proxy_url: str | None = None) -> str:
    normalized_base = (proxy_url or resolve_llm_proxy_url()).rstrip("/")
    return normalized_base + route_policy_path_prefix(route_policy) + "/v1"


def build_llm_proxy_codex_url(route_policy: str, *, proxy_url: str | None = None) -> str:
    return build_llm_proxy_openai_base_url(route_policy, proxy_url=proxy_url).rstrip("/") + "/codex/responses"


def _maybe_int(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return int(text)


def _maybe_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return float(text)


def _maybe_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def resolve_llm_client_config(raw: Any = None) -> LLMClientConfig:
    data: Mapping[str, Any]
    if raw is None:
        data = {}
    elif isinstance(raw, Mapping):
        data = raw
    elif hasattr(raw, "model_dump"):
        dumped = raw.model_dump(exclude_none=True)
        data = dumped if isinstance(dumped, Mapping) else {}
    else:
        data = {}
    return LLMClientConfig(
        route_policy=normalize_route_policy(
            data.get("route_policy")
            or os.getenv("LLM_CLIENT_ROUTE_POLICY")
            or os.getenv("ORCHESTRA_CORE_SGR_PROVIDER")
            or default_route_policy(),
        ),
        model=_maybe_text(data.get("model") or os.getenv("LLM_CLIENT_MODEL")),
        timeout_seconds=_maybe_int(data.get("timeout_seconds") or os.getenv("LLM_CLIENT_TIMEOUT_SECONDS")),
        temperature=_maybe_float(data.get("temperature") or os.getenv("LLM_CLIENT_TEMPERATURE")),
        max_tokens=_maybe_int(data.get("max_tokens") or os.getenv("LLM_CLIENT_MAX_TOKENS")),
        text_verbosity=_maybe_text(
            data.get("text_verbosity") or os.getenv("LLM_CLIENT_TEXT_VERBOSITY")
        ),
        reasoning_effort=_maybe_text(
            data.get("reasoning_effort") or os.getenv("LLM_CLIENT_REASONING_EFFORT")
        ),
        reasoning_summary=_maybe_text(
            data.get("reasoning_summary") or os.getenv("LLM_CLIENT_REASONING_SUMMARY")
        ),
    )
