from __future__ import annotations

from pathlib import Path
from typing import Any

from core.orchestra_agents.templates.opencode.agent_runtime.config_mcp_render import (
    render_server_config,
)


def build_mcp_block(
    config_dir: Path,
    cfg: dict[str, Any],
    agent_slug: str,
    working_dir: str,
) -> dict[str, Any]:
    servers = _mcp_servers(cfg)
    rendered: dict[str, Any] = {}
    for server in servers:
        name = str(server.get("name") or "").strip()
        if not name:
            continue
        rendered[name] = render_server_config(
            config_dir=config_dir,
            server=server,
            agent_slug=agent_slug,
            working_dir=working_dir,
        )
    return rendered


def _mcp_servers(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    servers = cfg.get("mcp_servers")
    if not isinstance(servers, list):
        return []
    normalized: list[dict[str, Any]] = []
    for server_item in servers:
        if isinstance(server_item, dict):
            normalized.append(server_item)
    return normalized
