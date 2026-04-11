from __future__ import annotations

from typing import Any


def extract_field(value: Any, name: str) -> Any:
    return getattr(value, name, None)


def resolve_sender_name(
    first_name: str,
    last_name: str,
    title: Any,
    username: str | None,
) -> str:
    if first_name:
        if last_name:
            return f"{first_name} {last_name}"
        return first_name
    if title:
        return str(title)
    if username:
        return f"@{username}"
    return "Unknown"


def extract_message_data(message: Any, sender: Any, chat: Any) -> dict[str, Any]:
    sender_name, username, user_id = extract_sender(sender)
    date_value = extract_field(message, "date")
    timestamp = date_value.isoformat() if date_value else None
    return {
        "chat_id": extract_chat_id(message),
        "chat_name": extract_chat_name(chat),
        "message_id": int(extract_field(message, "id") or 0),
        "sender_name": sender_name,
        "username": username,
        "user_id": user_id,
        "text": str(extract_field(message, "message") or ""),
        "timestamp": timestamp,
    }


def extract_chat_id(message: Any) -> str:
    peer = extract_field(message, "peer_id")
    if peer is None:
        return "unknown"
    for field_name in ("channel_id", "user_id", "chat_id"):
        field_value = extract_field(peer, field_name)
        if field_value is not None:
            return str(field_value)
    return "unknown"


def extract_chat_name(chat: Any) -> str:
    if chat is None:
        return "Unknown Chat"
    title = extract_field(chat, "title")
    if title:
        return str(title)
    first_name = str(extract_field(chat, "first_name") or "")
    last_name = str(extract_field(chat, "last_name") or "")
    if first_name and last_name:
        return f"{first_name} {last_name}"
    if first_name:
        return first_name
    return "Unknown Chat"


def extract_sender(sender: Any) -> tuple[str, str | None, str | None]:
    if sender is None:
        return "Unknown", None, None
    raw_user_id = extract_field(sender, "id")
    user_id = None if raw_user_id is None else str(raw_user_id)
    raw_username = extract_field(sender, "username")
    username = None if raw_username is None else str(raw_username)
    sender_name = resolve_sender_name(
        first_name=str(extract_field(sender, "first_name") or ""),
        last_name=str(extract_field(sender, "last_name") or ""),
        title=extract_field(sender, "title"),
        username=username,
    )
    return sender_name, username, user_id


async def extract_event_fields(event: Any) -> tuple[Any, Any, Any]:
    message = event.message
    sender = await event.get_sender()
    chat = await event.get_chat()
    return message, sender, chat
