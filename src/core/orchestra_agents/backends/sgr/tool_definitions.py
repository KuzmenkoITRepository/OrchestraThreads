"""OpenAI tool definitions for the SGR agent."""

from __future__ import annotations

from typing import Any

from core.orchestra_agents.backends.sgr.mcp_protocol import MCPServerProtocol
from core.orchestra_agents.backends.sgr.sgr_tools import SGRInternalTools
from core.orchestra_agents.backends.sgr.support.settings import normalize_optional_str

_OBJECT = "object"


def build_sgr_openai_tools(
    mcp_servers: dict[str, MCPServerProtocol],
    tool_schemas: list[dict[str, object]] | None = None,
) -> list[dict[str, Any]]:
    """Build the full list of OpenAI-compatible tool definitions."""
    tools = SGRInternalTools.build_openai_tools()
    tools.extend(_build_mcp_tools(mcp_servers, tool_schemas or []))
    return tools


def _build_mcp_tools(
    mcp_servers: dict[str, MCPServerProtocol],
    schemas: list[dict[str, object]],
) -> list[dict[str, Any]]:
    """Build MCP tool definitions from schemas or fallback to generic."""
    schema_map = _index_schemas(schemas)
    result: list[dict[str, Any]] = []
    for tool_name in sorted(mcp_servers.keys()):
        schema = schema_map.get(tool_name)
        if schema:
            result.append(_convert_tool_entry(schema))
        else:
            result.append(_generic_tool_entry(tool_name))
    return result


def _index_schemas(schemas: list[dict[str, object]]) -> dict[str, Any]:
    """Index tool schemas by name."""
    index: dict[str, Any] = {}
    for entry in schemas:
        name = normalize_optional_str(entry.get("name"))
        if name:
            index[name] = dict(entry)
    return index


def _convert_tool_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Convert an MCP tool entry to OpenAI function-calling format."""
    return {
        "type": "function",
        "function": {
            "name": str(entry.get("name") or ""),
            "description": str(entry.get("description") or "").strip(),
            "parameters": entry.get("inputSchema") or {"type": _OBJECT, "properties": {}},
        },
    }


def _generic_tool_entry(tool_name: str) -> dict[str, Any]:
    """Build a generic OpenAI function tool entry for an MCP tool."""
    return {
        "type": "function",
        "function": {
            "name": tool_name,
            "description": f"Call the {tool_name} MCP tool.",
            "parameters": {
                "type": _OBJECT,
                "properties": {"message": {"type": "string"}},
            },
        },
    }
