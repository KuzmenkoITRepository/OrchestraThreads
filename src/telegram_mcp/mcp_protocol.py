"""JSON-RPC helpers, payload builders, and tool/resource specs for Telegram MCP."""

from __future__ import annotations

import json
from typing import Any

JsonDict = dict[str, Any]

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "telegram-mcp"
SERVER_VERSION = "0.2.0"


class ServerHelpers:
    """JSON-RPC envelope builders and argument extraction."""

    @staticmethod
    def jsonrpc_result(request_id: object, result_payload: JsonDict) -> JsonDict:
        """Wrap a result payload in a JSON-RPC response."""
        return {"jsonrpc": "2.0", "id": request_id, "result": result_payload}

    @staticmethod
    def jsonrpc_error(request_id: object, code: int, message: str) -> JsonDict:
        """Wrap an error in a JSON-RPC response."""
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

    @staticmethod
    def initialize_result() -> JsonDict:
        """Build the MCP initialize response."""
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}, "resources": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        }

    @staticmethod
    def request_arguments(params: object) -> JsonDict:
        """Extract arguments dict from a tools/call params object."""
        arguments = params.get("arguments") if isinstance(params, dict) else None
        if isinstance(arguments, dict):
            return arguments
        return {}


class Payloads:
    """MCP tool/resource result builders."""

    @staticmethod
    def tool(name: str, description: str, input_schema: JsonDict) -> JsonDict:
        """Build a single MCP tool descriptor."""
        return {"name": name, "description": description, "inputSchema": input_schema}

    @staticmethod
    def result(payload: JsonDict, *, text: str | None = None) -> JsonDict:
        """Wrap a tool or resource result in MCP content format."""
        rendered = text or json.dumps(payload, ensure_ascii=False)
        return {
            "structuredContent": payload,
            "content": [{"type": "text", "text": rendered}],
        }

    @staticmethod
    def tools_result() -> JsonDict:
        """Build the tools/list response with all registered tool specs."""
        return {"tools": _tool_specs()}

    @staticmethod
    def resources_result() -> JsonDict:
        """Build the resources/list response."""
        return {"resources": _resource_specs()}

    @staticmethod
    def resource_templates_result() -> JsonDict:
        """Build the resources/templates/list response."""
        return {"resourceTemplates": _resource_templates()}


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


def _tool_specs() -> list[JsonDict]:
    int_schema = {"type": "integer"}
    str_schema = {"type": "string"}
    recipient_prop = {**str_schema, "description": "Recipient alias"}
    return [
        Payloads.tool(
            "send_telegram_message",
            "Send a Telegram message with optional formatting, reply, or media.",
            {
                "type": "object",
                "properties": {
                    "message": {**str_schema, "description": "Message text (max 4096 chars)"},
                    "recipient": recipient_prop,
                    "parse_mode": {**str_schema, "enum": ["markdown", "html"]},
                    "reply_to_message_id": {**int_schema, "description": "Message ID to reply to"},
                    "media": {
                        "type": "object",
                        "description": "Optional media attachment (base64 or file path)",
                        "properties": {
                            "type": {**str_schema, "enum": ["photo", "document", "voice"]},
                            "data": {**str_schema, "description": "Base64-encoded content"},
                            "path": {
                                **str_schema,
                                "description": "Local file path (alternative to data)",
                            },
                            "filename": str_schema,
                        },
                        "required": ["type"],
                    },
                    "thread_id": {
                        **str_schema,
                        "description": "Opaque thread ID for metadata linkage",
                    },
                },
                "required": ["message"],
            },
        ),
        Payloads.tool(
            "edit_telegram_message",
            "Edit a previously sent Telegram message.",
            {
                "type": "object",
                "properties": {
                    "message_id": {**int_schema, "description": "Telegram message ID to edit"},
                    "new_text": {**str_schema, "description": "Replacement message text"},
                    "recipient": recipient_prop,
                },
                "required": ["message_id", "new_text"],
            },
        ),
        Payloads.tool(
            "delete_telegram_message",
            "Delete a previously sent Telegram message.",
            {
                "type": "object",
                "properties": {
                    "message_id": {**int_schema, "description": "Telegram message ID to delete"},
                    "recipient": recipient_prop,
                },
                "required": ["message_id"],
            },
        ),
        Payloads.tool(
            "send_telegram_message_batch",
            "Send the same message to multiple recipients. Returns per-recipient results.",
            {
                "type": "object",
                "properties": {
                    "message": {**str_schema, "description": "Message text (max 4096 chars)"},
                    "recipients": {"type": "array", "items": str_schema},
                    "thread_id": {**str_schema, "description": "Opaque thread ID"},
                },
                "required": ["message", "recipients"],
            },
        ),
        Payloads.tool(
            "get_telegram_chat_info",
            "Get metadata for a Telegram chat or user (cached, TTL 5 min).",
            {
                "type": "object",
                "properties": {"recipient": recipient_prop},
                "required": ["recipient"],
            },
        ),
        Payloads.tool(
            "check_telegram_read_receipt",
            "Best-effort check whether a sent message was likely read. Non-authoritative.",
            {
                "type": "object",
                "properties": {
                    "message_id": {**int_schema, "description": "Telegram message ID"},
                    "recipient": recipient_prop,
                },
                "required": ["message_id"],
            },
        ),
        Payloads.tool(
            "upsert_recipient",
            "Add or update a recipient alias -> chat_id mapping at runtime.",
            {
                "type": "object",
                "properties": {
                    "alias": {**str_schema, "description": "Recipient alias"},
                    "chat_id": {**int_schema, "description": "Telegram chat ID"},
                },
                "required": ["alias", "chat_id"],
            },
        ),
        Payloads.tool(
            "remove_recipient",
            "Remove a recipient alias from the registry.",
            {
                "type": "object",
                "properties": {"alias": {**str_schema, "description": "Alias to remove"}},
                "required": ["alias"],
            },
        ),
    ]


def _resource_specs() -> list[JsonDict]:
    return [
        {
            "uri": "telegram://recipients",
            "name": "Telegram Recipients",
            "description": "Dynamic recipient registry: alias -> chat_id mapping.",
            "mimeType": "application/json",
        },
        {
            "uri": "telegram://rate_limits",
            "name": "Telegram Rate Limits",
            "description": "Current rate limit state for the Telegram client.",
            "mimeType": "application/json",
        },
    ]


def _resource_templates() -> list[JsonDict]:
    return [
        {
            "uriTemplate": "telegram://thread/{thread_id}/messages",
            "name": "Thread Messages",
            "description": "Messages linked to a specific orchestra thread.",
            "mimeType": "application/json",
        },
        {
            "uriTemplate": "telegram://chat/{recipient}/info",
            "name": "Chat Info",
            "description": "Cached metadata for a Telegram chat or user.",
            "mimeType": "application/json",
        },
    ]
