from __future__ import annotations

from core.orchestra_thread.mcp_tools_common import JSON_MAP, tool
from core.orchestra_thread.mcp_tools_context import string_schema


def list_thread_tools() -> list[JSON_MAP]:
    schema = string_schema()
    return [
        tool(
            "thread_send",
            "Send a thread message using compact auto-routing based on the active invocation context.",
            {
                "type": "object",
                "properties": {
                    "message": schema,
                    "target_agent_slug": schema,
                    "mode": {
                        "type": "string",
                        "enum": ["auto", "root", "child", "exact"],
                    },
                    "thread_id": schema,
                    "client_request_id": schema,
                },
                "required": ["message"],
            },
        ),
        tool(
            "thread_status",
            "Publish thread status updates without repeating thread_id when an active context exists.",
            {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["in_progress", "review", "done", "closed"],
                    },
                    "message": schema,
                    "thread_id": schema,
                    "target_agent_slug": schema,
                    "client_request_id": schema,
                },
                "required": ["status", "message"],
            },
        ),
        tool(
            "thread_current",
            "Return compact current-thread state for the active invocation.",
            {
                "type": "object",
                "properties": {
                    "thread_id": schema,
                },
            },
        ),
        tool(
            "thread_expand",
            "Expand thread details on demand. Use sparingly when compact state is insufficient.",
            {
                "type": "object",
                "properties": {
                    "thread_id": schema,
                    "view": {
                        "type": "string",
                        "enum": ["latest", "tail", "related", "full"],
                    },
                    "limit": {"type": "integer"},
                },
            },
        ),
        tool(
            "thread_guide",
            "Fetch the canonical OrchestraThreads workflow and routing/status rules from the service.",
            {
                "type": "object",
                "properties": {
                    "view": {
                        "type": "string",
                        "enum": ["compact", "full"],
                    },
                    "section": {
                        "type": "string",
                        "enum": [
                            "overview",
                            "workflow",
                            "routing",
                            "statuses",
                            "delivery",
                            "mcp",
                            "mcp_tools",
                        ],
                    },
                },
            },
        ),
        tool(
            "agent_status",
            "Fetch busy and online status for an agent without disturbing its active work.",
            {
                "type": "object",
                "properties": {
                    "agent_slug": schema,
                },
                "required": ["agent_slug"],
            },
        ),
    ]
