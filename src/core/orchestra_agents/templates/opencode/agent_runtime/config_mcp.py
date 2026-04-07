from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from core.orchestra_agents.templates.opencode.agent_runtime.config_threads import (
    build_threads_block,
)


def build_mcp_block(
    config_dir: Path,
    cfg: dict[str, Any],
    agent_slug: str,
    working_dir: str,
) -> dict[str, Any]:
    server = _find_threads_server(cfg)
    if server is None:
        return {}
    return {"orchestra_threads": build_threads_block(config_dir, server, agent_slug, working_dir)}


def _find_threads_server(cfg: dict[str, Any]) -> dict[str, Any] | None:
    servers = cfg.get("mcp_servers")
    if not isinstance(servers, list):
        return None
    for server_item in servers:
        if _is_threads_server(server_item):
            return cast(dict[str, Any], server_item)
    return None


def _is_threads_server(server_item: object) -> bool:
    if not isinstance(server_item, dict):
        return False
    server_name = str(server_item.get("name") or "").strip()
    return server_name == "orchestra_threads"
