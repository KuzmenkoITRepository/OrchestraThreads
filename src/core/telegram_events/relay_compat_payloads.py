from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

_PROTOCOL_VERSION = "2024-11-05"


def build_health_payload() -> dict[str, Any]:
    return {"ok": True, "service": "better-telegram-mcp"}


def build_sse_event_payload(message_data: dict[str, Any]) -> dict[str, Any]:
    raw_timestamp = message_data.get("timestamp")
    occurred_at = (
        raw_timestamp
        if isinstance(raw_timestamp, str) and raw_timestamp
        else datetime.now(tz=UTC).isoformat()
    )
    return {
        "event_id": uuid4().hex,
        "event_type": "message",
        "occurred_at": occurred_at,
        "mode": "private",
        "account": "telegram",
        "update": {
            "message": {
                "id": message_data.get("message_id", 0),
                "from": {
                    "id": _optional_int(message_data.get("user_id")),
                    "first_name": str(message_data.get("sender_name") or "Unknown"),
                },
                "chat": {
                    "id": _optional_int(message_data.get("chat_id")),
                    "title": str(message_data.get("chat_name") or "Private Chat"),
                },
                "text": str(message_data.get("text") or ""),
                "date": occurred_at,
            }
        },
    }


def build_initialize_result(request_id: Any) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "protocolVersion": _PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {
                "name": "better-telegram-mcp-compat",
                "version": "1.0.0",
            },
        },
    }


def build_tools_list_result(request_id: Any) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "tools": [
                {
                    "name": "send_telegram_message",
                    "description": "Send a Telegram message through the shared session",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "chat_id": {"type": ["string", "integer"]},
                            "recipient": {"type": "string"},
                            "message": {"type": "string"},
                        },
                        "required": ["message"],
                    },
                }
            ]
        },
    }


def build_send_result(request_id: Any, message_id: int) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {"content": [{"text": {"structuredContent": {"messageId": message_id}}}]},
    }


def build_rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _optional_int(raw_value: Any) -> int | None:
    try:
        return None if raw_value is None else int(raw_value)
    except (TypeError, ValueError):
        return None
