from __future__ import annotations

from typing import Any

from core.orchestra_agents.backends.agent_mux.normalization import normalize_bool, normalize_int

MIN_AGENT_TIMEOUT_SECONDS = 30
DEFAULT_AGENT_TIMEOUT_SECONDS = 1800
DEFAULT_CONTEXT_MEMORY_ENTRIES = 16


def base_runtime_settings(
    raw_config: dict[str, Any], *, working_dir: str, http_endpoint: str | None
) -> dict[str, Any]:
    return {
        "http_endpoint": str(http_endpoint or "").rstrip("/"),
        "agent_mux_binary": str(raw_config.get("agent_mux_binary") or "agent-mux").strip()
        or "agent-mux",
        "state_root": state_root(raw_config, working_dir=working_dir),
        "artifact_root": artifact_root(raw_config, working_dir=working_dir),
        "role": str(raw_config.get("role") or "worker").strip() or "worker",
        "variant": str(raw_config.get("variant") or "").strip() or None,
        "engine": str(raw_config.get("engine") or "codex").strip() or "codex",
    }


def limits_runtime_settings(raw_config: dict[str, Any]) -> dict[str, Any]:
    return {
        "max_attempts": max(1, normalize_int(raw_config.get("max_attempts"), default=3)),
        "agent_timeout_seconds": max(
            MIN_AGENT_TIMEOUT_SECONDS,
            normalize_int(raw_config.get("timeout_seconds"), default=DEFAULT_AGENT_TIMEOUT_SECONDS),
        ),
        "context_memory_entries": max(
            4,
            normalize_int(
                raw_config.get("context_memory_entries"),
                default=DEFAULT_CONTEXT_MEMORY_ENTRIES,
            ),
        ),
        "require_tool_call_for_response": normalize_bool(
            raw_config.get("require_tool_call_for_response"),
            default=False,
        ),
    }


def state_root(raw_config: dict[str, Any], *, working_dir: str) -> str:
    configured_root = str(raw_config.get("state_root") or "").strip()
    if configured_root:
        return configured_root
    return f"{working_dir}/runtime_state"


def artifact_root(raw_config: dict[str, Any], *, working_dir: str) -> str:
    configured_root = str(raw_config.get("artifact_root") or "").strip()
    if configured_root:
        return configured_root
    return f"{state_root(raw_config, working_dir=working_dir)}/artifacts"
