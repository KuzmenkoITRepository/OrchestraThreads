from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module
from typing import Any

from core.orchestra_agents.runtime import EventDelivery

JSONMap = dict[str, Any]
BackendConfig = dict[str, object]

OMNIROUTE_URL_KEY = "OMNIROUTE_URL"
OMNIROUTE_API_KEY = "OMNIROUTE_API_KEY"
SGR_AGENT_SLUG = "sgr"
NAME_KEY = "name"
MEMORY_TOOLS = frozenset(
    (
        "memory_remember",
        "memory_search",
        "memory_delete",
        "memory_clear",
        "memory_list_rooms",
        "memory_list_categories",
    ),
)


def load_mcp_loader() -> Any:
    return import_module("core.orchestra_agents.backends.sgr.mcp_loader")


def message_delivery(delivery_id: str, event_id: str) -> EventDelivery:
    return EventDelivery.from_dict(
        {
            "delivery_id": delivery_id,
            "events": [
                {
                    "event_id": event_id,
                    "thread_id": None,
                    "root_thread_id": None,
                    "parent_thread_id": None,
                    "owner_agent_slug": None,
                    "sequence_no": 10,
                    "event_kind": "message",
                    "notification_status": None,
                    "from_agent_slug": "secretary",
                    "to_agent_slug": "sgr",
                    "message_text": "Please confirm receipt.",
                    "interrupts_runtime": True,
                    "requires_response": True,
                    "created_at": "2026-04-03T07:10:00Z",
                },
            ],
        },
    )


def tool_call(tool_name: str, call_id: str) -> JSONMap:
    return {
        "id": call_id,
        "type": "function",
        "function": {
            NAME_KEY: tool_name,
            "arguments": "{}",
        },
    }


@dataclass
class RegistrationState:
    servers: dict[str, Any] = field(default_factory=dict)
    schemas: list[dict[str, Any]] = field(default_factory=list)


class FakeMCPServer:
    """Minimal MCP server stub for testing."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def handle_tools_call(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls.append(
            {
                NAME_KEY: name,
                "arguments": arguments,
            }
        )
        return {
            "content": [{"type": "text", "text": "ok"}],
            "structuredContent": {"ok": True},
        }

    async def close(self) -> None:
        """No-op close for testing."""
