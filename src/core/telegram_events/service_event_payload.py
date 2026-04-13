from __future__ import annotations

from typing import Any

_TELEGRAM_SOURCE = "telegram"
_TELEGRAM_EVENTS_AGENT = "telegram_events"
_TELEGRAM_MESSAGE_KIND = "telegram_message"


def build_message_event_payload(
    message_data: dict[str, Any],
    target_agent_slug: str = "secretary",
) -> dict[str, Any]:
    """Build the events-engine payload for a normal Telegram message."""
    event_id = _message_event_id(message_data)
    return {
        "delivery_id": event_id,
        "events": [
            {
                "event_id": event_id,
                "thread_id": None,
                "root_thread_id": None,
                "parent_thread_id": None,
                "owner_agent_slug": None,
                "sequence_no": None,
                "event_kind": _TELEGRAM_MESSAGE_KIND,
                "notification_status": None,
                "from_agent_slug": _TELEGRAM_EVENTS_AGENT,
                "to_agent_slug": target_agent_slug,
                "message_text": _message_prompt(message_data),
                "interrupts_runtime": False,
                "requires_response": True,
                "created_at": message_data["timestamp"],
                "metadata": message_metadata(message_data),
            }
        ],
    }


def build_delivery_payload(
    target_agent_slug: str,
    event_data: dict[str, Any],
) -> dict[str, Any]:
    """Wrap event data in the delivery contract expected by events-engine."""
    return {
        "agent_slug": target_agent_slug,
        "event_data": event_data,
    }


def message_metadata(message_data: dict[str, Any]) -> dict[str, Any]:
    """Build event metadata for an incoming Telegram message."""
    return {
        "source": _TELEGRAM_SOURCE,
        "chat_id": message_data["chat_id"],
        "message_id": message_data["message_id"],
        "sender_name": message_data["sender_name"],
        "username": message_data.get("username"),
        "user_id": message_data.get("user_id"),
    }


def _message_event_id(message_data: dict[str, Any]) -> str:
    chat_id = message_data["chat_id"]
    message_id = message_data["message_id"]
    return f"telegram_{chat_id}_{message_id}"


def _message_prompt(message_data: dict[str, Any]) -> str:
    prompt_parts = [
        "New Telegram message received:",
        f"From: {message_data['sender_name']}",
    ]
    username = message_data.get("username")
    if username:
        prompt_parts.append(f"Username: @{username}")
    prompt_parts.extend(
        [
            f"Chat: {message_data['chat_name']}",
            f"Time: {message_data['timestamp']}",
            "",
            "Message:",
            message_data["text"],
        ]
    )
    return "\n".join(prompt_parts)
