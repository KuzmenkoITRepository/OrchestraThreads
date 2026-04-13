"""Load MCP servers from manifest backend config."""

from __future__ import annotations

import importlib
import inspect
import logging
from collections.abc import Callable
from typing import Any, cast

from core.orchestra_agents.backends.sgr.mcp_protocol import MCPServerProtocol

logger = logging.getLogger(__name__)


def load_mcp_from_config(
    raw_config: dict[str, Any], *, agent_slug: str | None = None
) -> tuple[dict[str, MCPServerProtocol], list[dict[str, Any]]]:
    """Load MCP servers and tool schemas from backend config."""
    entries = raw_config.get("mcp_servers")
    if not entries or not isinstance(entries, list):
        return {}, []

    servers: dict[str, MCPServerProtocol] = {}
    schemas: list[dict[str, Any]] = []
    for entry in entries:
        _load_single_entry(entry, servers, schemas, agent_slug=agent_slug)
    return servers, schemas


def _load_single_entry(
    entry: dict[str, Any],
    servers: dict[str, MCPServerProtocol],
    schemas: list[dict[str, Any]],
    *,
    agent_slug: str | None = None,
) -> None:
    """Load a single MCP server entry from config."""
    module_path = str(entry.get("module") or "").strip()
    class_name = str(entry.get("class") or "").strip()
    if not module_path or not class_name:
        logger.warning("Skipping incomplete MCP entry: %s", entry)
        return

    server = _instantiate_server(module_path, class_name, agent_slug=agent_slug)
    if server is None:
        return

    tool_defs = _load_schemas_for_entry(entry)
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


def _instantiate_server(
    module_path: str,
    class_name: str,
    *,
    agent_slug: str | None = None,
) -> MCPServerProtocol | None:
    """Import and instantiate an MCP server class."""
    try:
        module = importlib.import_module(module_path)
    except Exception:
        logger.exception("Failed to import MCP module %s", module_path)
        return None

    server_cls = getattr(module, class_name, None)
    if not isinstance(server_cls, type):
        logger.error("MCP class %s not found in %s", class_name, module_path)
        return None

    server_factory = cast(Callable[..., object], server_cls)
    params = _init_params(server_factory, agent_slug)
    if params is None:
        return cast(MCPServerProtocol, server_factory())
    return cast(MCPServerProtocol, server_factory(**params))


def _init_params(
    server_cls: Callable[..., object],
    agent_slug: str | None,
) -> dict[str, Any] | None:
    """Build init params accepted by the constructor."""
    if not agent_slug:
        return None

    sig = inspect.signature(server_cls)
    for name, param in sig.parameters.items():
        if name == "agent_slug" and param.kind in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        ):
            return {"agent_slug": agent_slug}
    return None


def _load_schemas_for_entry(entry: dict[str, Any]) -> list[dict[str, Any]]:
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
