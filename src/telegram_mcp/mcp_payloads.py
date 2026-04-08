"""MCP tool/resource specs and text-field helpers."""

from __future__ import annotations

from telegram_mcp.mcp_protocol import JsonDict


def tools_result() -> JsonDict:
    """Build the tools/list response."""
    tool_schema: JsonDict = {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Message text (max 4096 chars)"},
            "recipient": {"type": "string", "description": "Recipient alias"},
        },
        "required": ["message"],
    }
    return {
        "tools": [
            {
                "name": "send_telegram_message",
                "description": "Send a Telegram message to a configured recipient.",
                "inputSchema": tool_schema,
            },
        ],
    }


def resources_result() -> JsonDict:
    """Build the resources/list response (empty)."""
    return {"resources": []}


def resource_templates_result() -> JsonDict:
    """Build the resources/templates/list response (empty)."""
    return {"resourceTemplates": []}


def normalize_optional_str(raw: object) -> str | None:
    """Normalize a value to a stripped string or None."""
    normalized = str(raw or "").strip()
    return normalized or None


def ensure_text(raw: object, *, field_name: str) -> str:
    """Normalize and validate a required text field."""
    normalized = str(raw or "").strip()
    if not normalized:
        raise RuntimeError(f"{field_name} is required")
    return normalized
