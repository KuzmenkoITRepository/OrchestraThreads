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

    assert settings.default_model == "cx/gpt-5.4-mini"


def test_omniroute_url_uses_direct_key() -> None:
    settings = build_runtime_settings(
        {"omniroute_url": "http://127.0.0.1:8104"},
        working_dir="/workspace/agents/orchestra",
        http_endpoint="http://orchestra-agent-orchestra:8787",
        llm_route_policy=None,
        llm_model=None,
    )
    assert settings.omniroute_url == "http://127.0.0.1:8104"


def test_omniroute_api_key_uses_direct_key() -> None:
    settings = build_runtime_settings(
        {"omniroute_api_key": "runtime-test-key"},
        working_dir="/workspace/agents/orchestra",
        http_endpoint="http://orchestra-agent-orchestra:8787",
        llm_route_policy=None,
        llm_model=None,
    )

    assert settings.omniroute_api_key == "runtime-test-key"


def test_unknown_inputs_keep_direct_keys() -> None:
    settings = build_runtime_settings(
        {
            "omniroute_url": "http://direct-omniroute:20128",
            "omniroute_api_key": "direct-key",
            "legacy_url": "http://legacy-proxy:8104",
            "legacy_api_key": "legacy-key",
        },
        working_dir="/workspace/agents/orchestra",
        http_endpoint="http://orchestra-agent-orchestra:8787",
        llm_route_policy=None,
        llm_model=None,
    )

    assert settings.omniroute_url == "http://direct-omniroute:20128"
    assert settings.omniroute_api_key == "direct-key"
