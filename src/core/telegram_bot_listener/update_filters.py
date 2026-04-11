from __future__ import annotations

from core.telegram_bot_listener.json_types import JsonDict


def is_private_chat(raw_chat: JsonDict) -> bool:
    return str(raw_chat.get("type")) == "private"


def extract_user_id(raw_user: object) -> int | None:
    if not isinstance(raw_user, dict):
        return None
    user_id = raw_user.get("id")
    if isinstance(user_id, int):
        return user_id
    return None
