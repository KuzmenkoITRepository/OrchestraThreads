from __future__ import annotations

import os

from core.orchestra_agents.backends.agent_mux.internal.toml_rendering import toml_quote

_DEFAULT_ALLOWED_ENV_KEYS: tuple[str, ...] = (
    "TELEGRAM_API_ID",
    "TELEGRAM_API_HASH",
    "TELEGRAM_SESSION_STRING",
    "TELEGRAM_CHAT_ID_IVAN",
    "LOG_LEVEL",
)
_HEADER_MAPPINGS: tuple[tuple[str, str], ...] = (
    ("X-Orchestra-Agent-Slug", "ORCHESTRA_AGENT_SLUG"),
    ("X-Orchestra-Context-Id", "ORCHESTRA_CONTEXT_ID"),
    ("X-Orchestra-Langfuse-Session-Id", "ORCHESTRA_CONTEXT_ID"),
)


def build_openai_base_url(route_policy: str, *, proxy_url: str) -> str:
    base = proxy_url.rstrip("/")
    return f"{base}{_route_policy_path_prefix(route_policy)}/v1"


def collect_allowed_env_values() -> dict[str, str]:
    allowed_keys = _allowed_env_keys()
    values: dict[str, str] = {}
    for key, value in os.environ.items():
        if key not in allowed_keys:
            continue
        values[key] = str(value)
    return values


def _allowed_env_keys() -> set[str]:
    allowed_keys = set(_DEFAULT_ALLOWED_ENV_KEYS)
    for item in os.getenv("AGENT_MUX_ALLOWED_ENV_VARS", "").split(","):
        normalized = item.strip()
        if normalized:
            allowed_keys.add(normalized)
    return allowed_keys


def base_config_lines(*, model: str, base_url: str, env_key: str | None) -> list[str]:
    lines = [
        f"model = {toml_quote(model)}",
        'web_search = "disabled"',
        'model_provider = "omniroute"',
        "",
        "[model_providers.omniroute]",
        'name = "OmniRoute/WET"',
        f"base_url = {toml_quote(base_url)}",
        'wire_api = "responses"',
        f"env_http_headers = {{ {_render_headers()} }}",
        "",
    ]
    if env_key:
        lines.insert(6, f"env_key = {toml_quote(env_key)}")
    return lines


def _route_policy_path_prefix(route_policy: str) -> str:
    normalized = route_policy.strip().lower().replace("-", "_")
    if normalized in {"codex", "codex_only"}:
        return "/codex"
    return ""


def _render_headers() -> str:
    return ", ".join(
        f"{toml_quote(header)} = {toml_quote(value)}" for header, value in _HEADER_MAPPINGS
    )
