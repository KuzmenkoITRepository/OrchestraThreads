"""Load MCP servers from manifest backend config."""

from __future__ import annotations

import importlib
import logging
from typing import Any

from core.orchestra_agents.backends.sgr import _mcp_config_interpolation as _interpolation
from core.orchestra_agents.backends.sgr import _mcp_remote_loader as _remote
from core.orchestra_agents.backends.sgr.mcp_protocol import MCPServerProtocol

logger = logging.getLogger(__name__)

_Servers = dict[str, MCPServerProtocol]
_Schemas = list[dict[str, Any]]


def load_mcp_from_config(raw_config: dict[str, Any]) -> tuple[_Servers, _Schemas]:
    """Load MCP servers and tool schemas from backend config."""
    interpolated = _interpolation.interpolate_config_values(raw_config)
    entries = interpolated.get("mcp_servers")
    if not entries or not isinstance(entries, list):
        return {}, []
    servers: _Servers = {}
    schemas: _Schemas = []
    for entry in entries:
        _load_single_entry(entry, servers, schemas)
    return servers, schemas


def _load_single_entry(
    entry: dict[str, Any],
    servers: _Servers,
    schemas: _Schemas,
) -> None:
    """Load a single MCP server entry from config."""
    transport = str(entry.get("transport") or "").strip()
    if transport == "http":
        _remote.load_http_entry(entry, servers, schemas)
        return

    _load_local_entry(entry, servers, schemas)


def _load_local_entry(
    entry: dict[str, Any],
    servers: _Servers,
    schemas: _Schemas,
) -> None:
    """Load a local Python module MCP server."""
    module_path = str(entry.get("module") or "").strip()
    class_name = str(entry.get("class") or "").strip()
    if not module_path or not class_name:
        logger.warning("Skipping incomplete MCP entry: %s", entry)
        return

    server = _instantiate_server(module_path, class_name)
    if server is None:
        return

    schema_fn_name = str(entry.get("schema_fn") or "").strip()
    tool_defs = _load_schemas(module_path, schema_fn_name)
    _register_tools(server, entry, tool_defs, servers, schemas)


def _instantiate_server(module_path: str, class_name: str) -> MCPServerProtocol | None:
    """Import and instantiate an MCP server class."""
    try:
        module = importlib.import_module(module_path)
    except Exception:
        logger.exception("Failed to import MCP module %s", module_path)
        return None

    server_cls = getattr(module, class_name, None)
    if server_cls is None:
        logger.error("MCP class %s not found in %s", class_name, module_path)
        return None
    return server_cls()  # type: ignore[no-any-return]


def _register_tools(
    server: MCPServerProtocol,
    entry: dict[str, Any],
    tool_defs: _Schemas,
    servers: _Servers,
    schemas: _Schemas,
) -> None:
    """Register server for each tool it exposes."""
    if tool_defs:
        for tool_def in tool_defs:
            tool_name = str(tool_def.get("name") or "").strip()
            if tool_name:
                servers[tool_name] = server
                schemas.append(dict(tool_def))
        return

    fallback = str(entry.get("name") or "").strip()
    if fallback:
        servers[fallback] = server


def _load_schemas(module_path: str, schema_fn_name: str) -> _Schemas:
    """Load tool schemas from a module function."""
    if not schema_fn_name:
        return []

    try:
        module = importlib.import_module(module_path)
    except Exception:
        logger.exception("Failed to import %s for schemas", module_path)
        return []

    schema_fn = getattr(module, schema_fn_name, None)
    if schema_fn is None:
        logger.error("Schema fn %s not found in %s", schema_fn_name, module_path)
        return []
    return [dict(td) for td in schema_fn()]
