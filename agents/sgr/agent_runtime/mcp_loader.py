"""Load MCP servers from manifest backend config."""

from __future__ import annotations

import importlib
import logging
from typing import Any

from agents.sgr.agent_runtime.mcp_protocol import MCPServerProtocol

logger = logging.getLogger(__name__)

_ToolMap = dict[str, MCPServerProtocol]
_SchemaList = list[dict[str, Any]]


def load_mcp_from_config(raw_config: dict[str, Any]) -> tuple[_ToolMap, _SchemaList]:
    """Load MCP servers and tool schemas from backend config."""
    entries = raw_config.get("mcp_servers")
    if not entries or not isinstance(entries, list):
        return {}, []
    servers: _ToolMap = {}
    schemas: _SchemaList = []
    for entry in entries:
        _load_single_entry(entry, servers, schemas)
    return servers, schemas


def _load_single_entry(
    entry: dict[str, Any],
    servers: _ToolMap,
    schemas: _SchemaList,
) -> None:
    """Load a single MCP server entry from config."""
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
    _register_server_tools(server, entry, tool_defs, servers, schemas)


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


def _register_server_tools(
    server: MCPServerProtocol,
    entry: dict[str, Any],
    tool_defs: _SchemaList,
    servers: _ToolMap,
    schemas: _SchemaList,
) -> None:
    """Register server for each tool it exposes."""
    if tool_defs:
        for tool_def in tool_defs:
            tool_name = str(tool_def.get("name") or "").strip()
            if tool_name:
                servers[tool_name] = server
                schemas.append(dict(tool_def))
        return
    fallback_name = str(entry.get("name") or "").strip()
    if fallback_name:
        servers[fallback_name] = server


def _load_schemas(module_path: str, schema_fn_name: str) -> _SchemaList:
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
