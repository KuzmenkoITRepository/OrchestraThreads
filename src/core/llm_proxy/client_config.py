from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

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

_MANAGED_AUTO_ALIASES: Final = frozenset(
    {
        "managed",
        "auto",
        "default",
        "managed_auto",
        "codex_proxy",
        "proxy",
    }
)
_CODEX_ONLY_ALIASES: Final = frozenset({"codex", "codex_only"})
_MINIMAX_ALIASES: Final = frozenset(
    {
        "minimax",
        "minimax_only",
        "fallback",
        "fallback_only",
    }
)
_LEGACY_ALIASES: Final = frozenset(
    {
        "legacy",
        "legacy_openai",
        "openai",
        "openai_compat",
        "openai_compatible",
    }
)


@dataclass(frozen=True)
class LLMClientConfig:
    """Resolved LLM client configuration."""

    route_policy: str = ROUTE_POLICY_MANAGED_AUTO
    model: str | None = None
    timeout_seconds: int | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    text_verbosity: str | None = None
    reasoning_effort: str | None = None
    reasoning_summary: str | None = None


def parse_csv(value: str | None) -> tuple[str, ...]:
    """Parse a comma-separated string into a tuple of non-empty trimmed parts."""
    if not value:
        return ()
    parts = [part.strip() for part in value.split(",")]
    return tuple(part for part in parts if part)


def normalize_route_policy(value: str | None, *, default: str = ROUTE_POLICY_MANAGED_AUTO) -> str:
    """Normalize a route policy string to one of the canonical values."""
    normalized = str(value or "").strip().lower().replace("-", "_")
    if not normalized:
        return default
    lookup: dict[frozenset[str], str] = {
        _MANAGED_AUTO_ALIASES: ROUTE_POLICY_MANAGED_AUTO,
        _CODEX_ONLY_ALIASES: ROUTE_POLICY_CODEX_ONLY,
        _MINIMAX_ALIASES: ROUTE_POLICY_MINIMAX_ONLY,
        _LEGACY_ALIASES: ROUTE_POLICY_LEGACY_OPENAI,
    }
    for aliases, policy in lookup.items():
        if normalized in aliases:
            return policy
    return default


def route_policy_path_prefix(route_policy: str) -> str:
    """Return the URL path prefix for the given route policy."""
    normalized = normalize_route_policy(route_policy)
    if normalized == ROUTE_POLICY_CODEX_ONLY:
        return "/codex"
    if normalized == ROUTE_POLICY_MINIMAX_ONLY:
        return "/minimax"
    return ""


def resolve_llm_proxy_url() -> str:
    """Resolve the LLM proxy base URL from environment."""
    return (
        os.getenv("LLM_PROXY_URL")
        or os.getenv("ORCHESTRA_CORE_CODEX_PROXY_URL")
        or DEFAULT_LLM_PROXY_URL
    ).strip()


def resolve_llm_proxy_api_key() -> str:
    """Resolve the LLM proxy API key from environment."""
    return (
        os.getenv("LLM_PROXY_API_KEY")
        or os.getenv("ORCHESTRA_CORE_CODEX_PROXY_API_KEY")
        or DEFAULT_LLM_PROXY_API_KEY
    ).strip()


def llm_proxy_enabled() -> bool:
    """Return True if the LLM proxy is enabled."""
    env_value = os.getenv("LLM_PROXY_ENABLED")
    if env_value is None:
        return True
    return env_value.strip().lower() in {"1", "true", "yes", "on"}


def default_route_policy() -> str:
    """Return the default route policy from environment."""
    return normalize_route_policy(
        os.getenv("LLM_PROXY_DEFAULT_ROUTE_POLICY") or ROUTE_POLICY_MANAGED_AUTO,
    )


def build_llm_proxy_openai_base_url(route_policy: str, *, proxy_url: str | None = None) -> str:
    """Build the OpenAI-compatible base URL for the given route policy."""
    base = (proxy_url or resolve_llm_proxy_url()).rstrip("/")
    prefix = route_policy_path_prefix(route_policy)
    return f"{base}{prefix}/v1"


def build_llm_proxy_codex_url(route_policy: str, *, proxy_url: str | None = None) -> str:
    """Build the Codex responses URL for the given route policy."""
    openai_url = build_llm_proxy_openai_base_url(route_policy, proxy_url=proxy_url).rstrip("/")
    return f"{openai_url}/codex/responses"


def _maybe_int(raw: Any) -> int | None:
    if raw is None:
        return None
    text = str(raw).strip()
    return int(text) if text else None


def _maybe_float(raw: Any) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip()
    return float(text) if text else None


def _maybe_text(raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _resolve_data(raw: Any) -> Mapping[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, Mapping):
        return raw
    if hasattr(raw, "model_dump"):
        dumped = raw.model_dump(exclude_none=True)
        return dumped if isinstance(dumped, Mapping) else {}
    return {}


def _resolve_policy(source: Mapping[str, Any]) -> str:
    return normalize_route_policy(
        source.get("route_policy")
        or os.getenv("LLM_CLIENT_ROUTE_POLICY")
        or os.getenv("ORCHESTRA_CORE_SGR_PROVIDER")
        or default_route_policy(),
    )


def resolve_llm_client_config(raw: Any = None) -> LLMClientConfig:
    """Build a full LLMClientConfig from raw input and environment fallbacks."""
    source = _resolve_data(raw)
    return LLMClientConfig(
        route_policy=_resolve_policy(source),
        model=_maybe_text(source.get("model") or os.getenv("LLM_CLIENT_MODEL")),
        timeout_seconds=_maybe_int(
            source.get("timeout_seconds") or os.getenv("LLM_CLIENT_TIMEOUT_SECONDS"),
        ),
        temperature=_maybe_float(
            source.get("temperature") or os.getenv("LLM_CLIENT_TEMPERATURE"),
        ),
        max_tokens=_maybe_int(
            source.get("max_tokens") or os.getenv("LLM_CLIENT_MAX_TOKENS"),
        ),
        text_verbosity=_maybe_text(
            source.get("text_verbosity") or os.getenv("LLM_CLIENT_TEXT_VERBOSITY"),
        ),
        reasoning_effort=_maybe_text(
            source.get("reasoning_effort") or os.getenv("LLM_CLIENT_REASONING_EFFORT"),
        ),
        reasoning_summary=_maybe_text(
            source.get("reasoning_summary") or os.getenv("LLM_CLIENT_REASONING_SUMMARY"),
        ),
    )
