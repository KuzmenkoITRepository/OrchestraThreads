from __future__ import annotations

from core.orchestra_agents.backends.agent_mux.backend_settings import build_runtime_settings


def test_default_model_uses_kiro_alias() -> None:
    settings = build_runtime_settings(
        {},
        working_dir="/workspace/agents/orchestra",
        http_endpoint="http://orchestra-agent-orchestra:8787",
        llm_route_policy=None,
        llm_model=None,
    )

    assert settings.default_model == "cx/gpt-5.1-codex-mini"


def test_llm_proxy_url_alias_sets_omniroute_url() -> None:
    settings = build_runtime_settings(
        {"llm_proxy_url": "http://127.0.0.1:8104"},
        working_dir="/workspace/agents/orchestra",
        http_endpoint="http://orchestra-agent-orchestra:8787",
        llm_route_policy=None,
        llm_model=None,
    )

    assert settings.omniroute_url == "http://127.0.0.1:8104"


def test_llm_proxy_api_key_alias_sets_runtime_key() -> None:
    settings = build_runtime_settings(
        {"llm_proxy_api_key": "runtime-test-key"},
        working_dir="/workspace/agents/orchestra",
        http_endpoint="http://orchestra-agent-orchestra:8787",
        llm_route_policy=None,
        llm_model=None,
    )

    assert settings.omniroute_api_key == "runtime-test-key"
