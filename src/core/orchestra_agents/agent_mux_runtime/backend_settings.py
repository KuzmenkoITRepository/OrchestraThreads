from __future__ import annotations

from typing import Any

from core.llm_proxy.client_config import default_route_policy, resolve_llm_client_config
from core.orchestra_agents.agent_mux_runtime.models import AgentMuxRuntimeSettings
from core.orchestra_agents.agent_mux_runtime.normalization import normalize_bool, normalize_int


def build_runtime_settings(
    raw_config: dict[str, Any],
    *,
    working_dir: str,
    http_endpoint: str | None,
    llm_route_policy: str | None,
    llm_model: str | None,
) -> AgentMuxRuntimeSettings:
    llm_config = resolve_llm_client_config(
        {
            "route_policy": raw_config.get("llm_route_policy") or default_route_policy(),
            "model": raw_config.get("model") or llm_model,
            "timeout_seconds": raw_config.get("timeout_seconds"),
            "reasoning_effort": raw_config.get("reasoning_effort"),
            "reasoning_summary": raw_config.get("reasoning_summary"),
            "text_verbosity": raw_config.get("text_verbosity"),
        }
    )
    settings_kwargs = {
        **_base_runtime_settings(raw_config, working_dir=working_dir, http_endpoint=http_endpoint),
        **_llm_runtime_settings(
            raw_config,
            llm_config=llm_config,
            llm_route_policy=llm_route_policy,
            llm_model=llm_model,
        ),
        **_limits_runtime_settings(raw_config),
        "mcp_servers": tuple(raw_config.get("mcp_servers") or ()),
    }
    return AgentMuxRuntimeSettings(**settings_kwargs)


def _base_runtime_settings(
    raw_config: dict[str, Any], *, working_dir: str, http_endpoint: str | None
) -> dict[str, Any]:
    return {
        "http_endpoint": str(http_endpoint or "").rstrip("/"),
        "agent_mux_binary": _agent_mux_binary(raw_config),
        "state_root": _state_root(raw_config, working_dir=working_dir),
        "artifact_root": _artifact_root(raw_config, working_dir=working_dir),
        "role": str(raw_config.get("role") or "worker").strip() or "worker",
        "variant": str(raw_config.get("variant") or "").strip() or None,
        "engine": str(raw_config.get("engine") or "codex").strip() or "codex",
    }


def _llm_runtime_settings(
    raw_config: dict[str, Any],
    *,
    llm_config: Any,
    llm_route_policy: str | None,
    llm_model: str | None,
) -> dict[str, Any]:
    return {
        "llm_proxy_url": str(raw_config.get("llm_proxy_url") or "http://127.0.0.1:8787").rstrip(
            "/"
        ),
        "llm_proxy_api_key": str(raw_config.get("llm_proxy_api_key") or "llm-proxy").strip()
        or "llm-proxy",
        "llm_route_policy": str(llm_route_policy or llm_config.route_policy or "codex_only").strip()
        or "codex_only",
        "default_model": str(llm_model or llm_config.model or "gpt-5.4").strip() or "gpt-5.4",
    }


def _limits_runtime_settings(raw_config: dict[str, Any]) -> dict[str, Any]:
    return {
        "max_attempts": max(1, normalize_int(raw_config.get("max_attempts"), default=3)),
        "agent_timeout_seconds": max(
            30, normalize_int(raw_config.get("timeout_seconds"), default=1800)
        ),
        "context_memory_entries": max(
            4,
            normalize_int(raw_config.get("context_memory_entries"), default=16),
        ),
        "require_tool_call_for_response": normalize_bool(
            raw_config.get("require_tool_call_for_response"),
            default=False,
        ),
    }


def _state_root(raw_config: dict[str, Any], *, working_dir: str) -> str:
    configured = str(raw_config.get("state_root") or "").strip()
    if configured:
        return configured
    return f"{working_dir}/runtime_state"


def _artifact_root(raw_config: dict[str, Any], *, working_dir: str) -> str:
    configured = str(raw_config.get("artifact_root") or "").strip()
    if configured:
        return configured
    return f"{_state_root(raw_config, working_dir=working_dir)}/artifacts"


def _agent_mux_binary(raw_config: dict[str, Any]) -> str:
    return str(raw_config.get("agent_mux_binary") or "agent-mux").strip() or "agent-mux"
