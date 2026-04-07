from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.orchestra_agents.agent_mux_runtime.codex_config_servers import render_server_block
from core.orchestra_agents.agent_mux_runtime.toml_rendering import toml_quote


def _build_openai_base_url(route_policy: str, *, proxy_url: str) -> str:
    """Build OpenAI-compatible base URL for the given route policy."""
    base = proxy_url.rstrip("/")
    prefix = _route_policy_path_prefix(route_policy)
    return f"{base}{prefix}/v1"


def _route_policy_path_prefix(route_policy: str) -> str:
    """Return URL path prefix for the given route policy."""
    normalized = route_policy.strip().lower().replace("-", "_")
    if normalized in {"codex", "codex_only"}:
        return "/codex"
    return ""


@dataclass(frozen=True)
class RuntimeCodexConfigRequest:
    codex_home: Path
    llm_proxy_url: str
    route_policy: str
    model: str
    mcp_servers: Sequence[Mapping[str, Any]] | None = None
    variables: Mapping[str, str] | None = None


def _build_request_variables(
    *,
    agent_slug: str,
    active_context_path: str,
    pythonpath: str,
    agent_working_dir: str,
) -> dict[str, str]:
    variables = {
        "agent_slug": str(agent_slug),
        "active_context_path": str(active_context_path),
        "pythonpath": str(pythonpath),
        "agent_working_dir": str(agent_working_dir),
        "working_dir": str(agent_working_dir),
    }
    for key, value in os.environ.items():
        variables[f"env.{key}"] = str(value)
    return variables


def create_runtime_codex_request(
    settings: RuntimeCodexConfigRequest,
    *,
    agent_slug: str,
    active_context_path: str,
    pythonpath: str,
    agent_working_dir: str,
) -> RuntimeCodexConfigRequest:
    return RuntimeCodexConfigRequest(
        codex_home=settings.codex_home,
        llm_proxy_url=settings.llm_proxy_url,
        route_policy=settings.route_policy,
        model=settings.model,
        mcp_servers=settings.mcp_servers,
        variables=_build_request_variables(
            agent_slug=agent_slug,
            active_context_path=active_context_path,
            pythonpath=pythonpath,
            agent_working_dir=agent_working_dir,
        ),
    )


def write_runtime_codex_config(
    request: RuntimeCodexConfigRequest,
) -> Path:
    config_path = request.codex_home / ".codex" / "config.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    lines = _base_config_lines(
        model=request.model,
        base_url=_build_openai_base_url(
            request.route_policy,
            proxy_url=request.llm_proxy_url,
        ),
    )
    variables = dict(request.variables or {})
    for item in request.mcp_servers or []:
        rendered = render_server_block(item, variables)
        if not rendered:
            continue
        lines.extend(rendered)
    config_path.write_text("\n".join(lines), encoding="utf-8")
    return config_path


def _base_config_lines(*, model: str, base_url: str) -> list[str]:
    return [
        f"model = {toml_quote(model)}",
        'model_provider = "omniroute"',
        "",
        "[model_providers.omniroute]",
        'name = "OmniRoute/WET"',
        f"base_url = {toml_quote(base_url)}",
        'env_key = "LLM_PROXY_API_KEY"',
        'wire_api = "responses"',
        'env_http_headers = { "X-Orchestra-Agent-Slug" = "ORCHESTRA_AGENT_SLUG", "X-Orchestra-Context-Id" = "ORCHESTRA_CONTEXT_ID", "X-Orchestra-Langfuse-Session-Id" = "ORCHESTRA_CONTEXT_ID" }',
        "",
    ]
