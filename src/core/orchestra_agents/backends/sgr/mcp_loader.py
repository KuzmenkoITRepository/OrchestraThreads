"""Load MCP servers from manifest backend config."""

from __future__ import annotations

import importlib
import logging
from typing import Any

from core.orchestra_agents.backends.sgr.mcp_protocol import MCPServerProtocol

logger = logging.getLogger(__name__)

_ToolMap = dict[str, MCPServerProtocol]
_SchemaList = list[dict[str, Any]]


def load_mcp_from_config(
    raw_config: dict[str, Any], *, agent_slug: str | None = None
) -> tuple[_ToolMap, _SchemaList]:
    """Load MCP servers and tool schemas from backend config."""
    entries = raw_config.get("mcp_servers")
    if not entries or not isinstance(entries, list):
        return {}, []
    servers: _ToolMap = {}
    schemas: _SchemaList = []
    for entry in entries:
        _load_single_entry(entry, servers, schemas, agent_slug=agent_slug)
    return servers, schemas


def _extract_module_path(entry: dict[str, Any]) -> str:
    """Extract module path from entry."""
    return str(entry.get("module") or "").strip()


def _extract_class_name(entry: dict[str, Any]) -> str:
    """Extract class name from entry."""
    return str(entry.get("class") or "").strip()


def _build_init_params(agent_slug: str | None) -> dict[str, str] | None:
    """Build init params for MCP server."""
    if not agent_slug:
        return None
    return {"agent_slug": agent_slug}


def _load_single_entry(
    entry: dict[str, Any],
    servers: _ToolMap,
    schemas: _SchemaList,
    *,
    agent_slug: str | None = None,
) -> None:
    """Load a single MCP server entry from config."""
    module_path = _extract_module_path(entry)
    class_name = _extract_class_name(entry)
    if not module_path or not class_name:
        logger.warning("Skipping incomplete MCP entry: %s", entry)
        return
    server = _instantiate_server(module_path, class_name, _build_init_params(agent_slug))
    if server is None:
        return
    _register_with_tools(server, entry, schemas, servers)


def _instantiate_server(
    module_path: str,
    class_name: str,
    init_params: dict[str, Any] | None = None,
) -> MCPServerProtocol | None:
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
    # Filter init_params to only pass what the constructor accepts
    params = _filter_init_params(server_cls, init_params)
    return server_cls(**params) if params is not None else server_cls()



def _filter_init_params(
    server_cls: type,
    init_params: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Filter init_params to only include what the constructor accepts."""
    if not init_params:
        return None
    import inspect

    sig = inspect.signature(server_cls.__init__)
    valid = {
        name
        for name, param in sig.parameters.items()
        if param.kind
        in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    }
    return {k: v for k, v in init_params.items() if k in valid} or None


def _register_with_tools(
    server: MCPServerProtocol,
    entry: dict[str, Any],
    schemas: _SchemaList,
    servers: _ToolMap,
) -> None:
    """Load schemas and register server tools."""
    tool_defs = _load_schemas_for_entry(entry)
    _register_server_tools(server, entry, tool_defs, servers, schemas)


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


def _load_schemas_for_entry(entry: dict[str, Any]) -> _SchemaList:
    """Load tool schemas from entry's schema_fn."""
    module_path = str(entry.get("module") or "").strip()
    schema_fn_name = str(entry.get("schema_fn") or "").strip()
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
