"""OpenAI tool definitions for the SGR Minimax agent."""

from __future__ import annotations

from typing import Any

from agents.sgr.agent_runtime.sgr_tools import SGRInternalTools
from agents.sgr.agent_runtime.support.settings import normalize_optional_str

_STRING = "string"
_OBJECT = "object"


def _tool_entry(
    name: str,
    description: str,
    properties: dict[str, dict[str, Any]],
    required: list[str] | None = None,
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": _OBJECT,
        "properties": properties,
    }
    if required:
        schema["required"] = required
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": schema,
        },
    }


def _string_prop() -> dict[str, str]:
    return {"type": _STRING}


def _enum_prop(values: list[str]) -> dict[str, Any]:
    return {"type": _STRING, "enum": values}


def build_sgr_openai_tools() -> list[dict[str, Any]]:
    """Build the full list of OpenAI-compatible tool definitions."""
    return SGRInternalTools.build_openai_tools() + [
        _tool_entry(
            "thread_send",
            "Send a thread message using compact auto-routing based on the active invocation context.",
            {
                "message": _string_prop(),
                "target_agent_slug": _string_prop(),
                "mode": _enum_prop(["auto", "root", "child", "exact"]),
                "thread_id": _string_prop(),
                "client_request_id": _string_prop(),
            },
            required=["message"],
        ),
        _tool_entry(
            "thread_status",
            "Publish thread status updates without repeating thread_id when an active context exists.",
            {
                "status": _enum_prop(["in_progress", "review", "done", "closed"]),
                "message": _string_prop(),
                "thread_id": _string_prop(),
                "target_agent_slug": _string_prop(),
                "client_request_id": _string_prop(),
            },
            required=["status", "message"],
        ),
        _tool_entry(
            "thread_current",
            "Return compact current-thread state for the active invocation.",
            {"thread_id": _string_prop()},
        ),
        _tool_entry(
            "thread_expand",
            "Expand thread details on demand. Use sparingly when compact state is insufficient.",
            {
                "thread_id": _string_prop(),
                "view": _enum_prop(["latest", "tail", "related", "full"]),
                "limit": {"type": "integer"},
            },
        ),
        _tool_entry(
            "thread_guide",
            "Fetch the canonical OrchestraThreads workflow and routing/status rules from the service.",
            {
                "view": _enum_prop(["compact", "full"]),
                "section": _enum_prop(
                    [
                        "overview",
                        "workflow",
                        "routing",
                        "statuses",
                        "delivery",
                        "mcp",
                        "mcp_tools",
                    ]
                ),
            },
        ),
    ]


def convert_tool_entry(entry: dict[str, Any]) -> dict[str, Any] | None:
    """Convert a raw tool entry dict to OpenAI function-calling format."""
    if not isinstance(entry, dict):
        return None
    name = normalize_optional_str(entry.get("name"))
    if not name:
        return None
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": str(entry.get("description") or "").strip(),
            "parameters": entry.get("inputSchema") or {"type": _OBJECT, "properties": {}},
        },
    }
