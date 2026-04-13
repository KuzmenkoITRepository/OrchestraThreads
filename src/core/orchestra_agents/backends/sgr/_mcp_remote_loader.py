"""Load remote HTTP MCP servers from manifest config."""

from __future__ import annotations

import logging
from typing import Any

from core.orchestra_agents.backends.sgr.mcp_protocol import MCPServerProtocol
from core.orchestra_agents.backends.sgr.mcp_remote_client import create_remote_server

logger = logging.getLogger(__name__)

_Servers = dict[str, MCPServerProtocol]
_Schemas = list[dict[str, Any]]


def load_http_entry(
    entry: dict[str, Any],
    servers: _Servers,
    schemas: _Schemas,
) -> None:
    """Load a remote HTTP MCP server entry from config."""
    url = str(entry.get("url") or "").strip()
    if not url:
        logger.warning("Skipping remote MCP entry without URL: %s", entry)
        return

    bearer_token = str(entry.get("bearer_token") or "").strip()
    if not bearer_token:
        logger.error("Remote MCP entry missing bearer_token: %s", entry.get("name"))
        return

    server = _create_server_if_valid(entry, url, bearer_token)
    if server is None:
        return

    _register_server_tools(server, entry, servers, schemas)


def _create_server_if_valid(
    entry: dict[str, Any],
    url: str,
    bearer_token: str,
) -> MCPServerProtocol | None:
    """Create remote server or return None on failure."""
    tools_list = _parse_enabled_tools(entry)
    timeout = int(entry.get("timeout_seconds", 30))
    try:
        return create_remote_server(
            url=url,
            bearer_token=bearer_token,
            tools=tools_list,
            timeout_seconds=timeout,
        )
    except Exception:
        logger.exception("Failed to create remote MCP server for %s", url)
        return None


def _parse_enabled_tools(entry: dict[str, Any]) -> list[str] | None:
    """Parse enabled_tools from config entry."""
    enabled_tools = entry.get("enabled_tools")
    if not enabled_tools or not isinstance(enabled_tools, list):
        return None
    return [str(t) for t in enabled_tools if str(t).strip()]


def _register_server_tools(
    server: MCPServerProtocol,
    entry: dict[str, Any],
    servers: _Servers,
    schemas: _Schemas,
) -> None:
    """Register remote server tools by name or fallback."""
    tools_list = _parse_enabled_tools(entry)
    if tools_list:
        for tool_name in tools_list:
            servers[tool_name] = server
            schemas.append(
                {
                    "name": tool_name,
                    "description": f"Remote tool via {entry.get('name', 'unknown')}",
                }
            )
        return

    fallback = str(entry.get("name") or "").strip()
    if fallback:
        servers[fallback] = server
