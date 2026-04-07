from __future__ import annotations

from core.orchestra_memory.mcp_tools_common import JSON_MAP, tool


def _string_schema() -> JSON_MAP:
    return {"type": "string"}


def list_memory_tools() -> list[JSON_MAP]:
    schema = _string_schema()
    return [
        tool(
            "memory_remember",
            "Store a memory entry scoped to the current agent.",
            {
                "type": "object",
                "properties": {
                    "text": schema,
                    "room": schema,
                    "category": schema,
                    "agent_slug": schema,
                },
                "required": ["text", "room", "category"],
            },
        ),
        tool(
            "memory_search",
            "Search memory entries scoped to the current agent.",
            {
                "type": "object",
                "properties": {
                    "query": schema,
                    "room": schema,
                    "category": schema,
                    "limit": {"type": "integer"},
                    "agent_slug": schema,
                },
            },
        ),
        tool(
            "memory_delete",
            "Delete one memory entry scoped to the current agent.",
            {
                "type": "object",
                "properties": {
                    "memory_id": schema,
                    "agent_slug": schema,
                },
                "required": ["memory_id"],
            },
        ),
        tool(
            "memory_clear",
            "Clear memory entries scoped to the current agent, optionally filtered by room/category.",
            {
                "type": "object",
                "properties": {
                    "room": schema,
                    "category": schema,
                    "agent_slug": schema,
                },
            },
        ),
    ]
