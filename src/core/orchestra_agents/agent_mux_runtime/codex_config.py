from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.orchestra_agents.agent_mux_runtime.codex_config_helpers import (
    base_config_lines,
    build_openai_base_url,
    collect_allowed_env_values,
)
from core.orchestra_agents.agent_mux_runtime.codex_config_servers import render_server_block


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
    for key, value in collect_allowed_env_values().items():
        variables[f"env.{key}"] = value
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
    lines = base_config_lines(
        model=request.model,
        base_url=build_openai_base_url(
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
