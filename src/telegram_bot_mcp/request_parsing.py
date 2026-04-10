from __future__ import annotations

from telegram_bot_mcp.mcp.protocol import JsonDict


def required_user_id(arguments: JsonDict) -> int:
    user_id = arguments.get("telegram_user_id")
    if not isinstance(user_id, int):
        raise ValueError("telegram_user_id is required")
    return user_id


def required_text(arguments: JsonDict, *, field_name: str) -> str:
    text = str(arguments.get(field_name) or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required")
    return text
