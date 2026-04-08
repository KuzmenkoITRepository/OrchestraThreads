from __future__ import annotations

from core.orchestra_agents.agent_mux_runtime.backend_settings import build_runtime_settings


def test_default_model_uses_kiro_alias() -> None:
    settings = build_runtime_settings(
        {},
        working_dir="/workspace/agents/orchestra",
        http_endpoint="http://orchestra-agent-orchestra:8787",
        llm_route_policy=None,
        llm_model=None,
    )

    assert settings.default_model == "cx/gpt-5.1-codex-mini"
