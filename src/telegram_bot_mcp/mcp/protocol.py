from __future__ import annotations

import json
from typing import Any

JsonDict = dict[str, Any]
PROTOCOL_VERSION = "2024-11-05"
INTEGER_FIELD_SCHEMA = (("type", "integer"),)


class ServerHelpers:
    @staticmethod
    def jsonrpc_result(request_id: Any, result: JsonDict) -> JsonDict:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def jsonrpc_error(request_id: Any, code: int, message: str) -> JsonDict:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

    @staticmethod
    def initialize_result() -> JsonDict:
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}, "resources": {}},
            "serverInfo": {"name": "telegram-bot-mcp", "version": "0.1.0"},
        }

    @staticmethod
    def resources_result() -> JsonDict:
        return {"resources": []}

    @staticmethod
    def resource_templates_result() -> JsonDict:
        return {"resourceTemplates": []}

    @staticmethod
    def request_arguments(params: Any) -> JsonDict:
        arguments = params.get("arguments") if isinstance(params, dict) else None
        if isinstance(arguments, dict):
            return arguments
        return {}


class Payloads:
    @staticmethod
    def tool(name: str, description: str, schema: JsonDict) -> JsonDict:
        return {"name": name, "description": description, "inputSchema": schema}

    @staticmethod
    def result(payload: JsonDict) -> JsonDict:
        return {
            "structuredContent": payload,
            "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        }

    @staticmethod
    def tools_result() -> JsonDict:
        return {"tools": _tool_specs()}


def _tool_specs() -> list[JsonDict]:
    return [
        Payloads.tool(
            "send_telegram_bot_message",
            "Send a Telegram bot message to a whitelisted private user.",
            _user_schema(),
        ),
        Payloads.tool(
            "send_telegram_bot_buttons",
            "Send a Telegram bot message with inline buttons.",
            _buttons_schema(),
        ),
        Payloads.tool(
            "create_telegram_bot_survey",
            "Create a Telegram bot survey session with button questions.",
            _survey_schema(),
        ),
        Payloads.tool(
            "get_telegram_bot_history",
            "Read agent-readable Telegram bot history.",
            _history_schema(),
        ),
    ]


def _user_schema() -> JsonDict:
    return {
        "type": "object",
        "properties": {"telegram_user_id": dict(INTEGER_FIELD_SCHEMA), "text": {"type": "string"}},
        "required": ["telegram_user_id", "text"],
    }


def _buttons_schema() -> JsonDict:
    return {
        "type": "object",
        "properties": {
            "telegram_user_id": dict(INTEGER_FIELD_SCHEMA),
            "text": {"type": "string"},
            "buttons": {"type": "array"},
        },
        "required": ["telegram_user_id", "text", "buttons"],
    }


def _survey_schema() -> JsonDict:
    return {
        "type": "object",
        "properties": {
            "telegram_user_id": dict(INTEGER_FIELD_SCHEMA),
            "title": {"type": "string"},
            "questions": {"type": "array"},
        },
        "required": ["telegram_user_id", "title", "questions"],
    }


def _history_schema() -> JsonDict:
    return {
        "type": "object",
        "properties": {
            "telegram_user_id": dict(INTEGER_FIELD_SCHEMA),
            "session_id": {"type": "string"},
            "limit": {"type": "integer"},
        },
        "required": ["telegram_user_id"],
    }
