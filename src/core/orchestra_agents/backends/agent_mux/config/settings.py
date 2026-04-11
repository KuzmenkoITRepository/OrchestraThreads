from __future__ import annotations

from typing import Any

from core.orchestra_agents.backends.agent_mux.config.models import AgentMuxRuntimeSettings
from core.orchestra_agents.backends.agent_mux.config.settings_llm import (
    llm_runtime_settings,
    resolve_llm_client_config,
)
from core.orchestra_agents.backends.agent_mux.config.settings_runtime import (
    base_runtime_settings,
    limits_runtime_settings,
)


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
            "route_policy": raw_config.get("llm_route_policy"),
            "model": raw_config.get("model") or llm_model,
            "timeout_seconds": raw_config.get("timeout_seconds"),
            "reasoning_effort": raw_config.get("reasoning_effort"),
            "reasoning_summary": raw_config.get("reasoning_summary"),
            "text_verbosity": raw_config.get("text_verbosity"),
        }
    )
    settings_kwargs = {
        **base_runtime_settings(raw_config, working_dir=working_dir, http_endpoint=http_endpoint),
        **llm_runtime_settings(
            raw_config,
            llm_config=llm_config,
            llm_route_policy=llm_route_policy,
            llm_model=llm_model,
        ),
        **limits_runtime_settings(raw_config),
        "mcp_servers": tuple(raw_config.get("mcp_servers") or ()),
    }
    return AgentMuxRuntimeSettings(**settings_kwargs)
