from __future__ import annotations

import uuid
from typing import Any

from core.telegram_events.service_logging import logger

_CLEAR_COMMAND = "/clear"
_CLEAR_RESTART_PROMPT = (
    "System event: the secretary session context was cleared after a /clear command. "
    "Reply in Telegram now by calling send_telegram_message with recipient 'ivan' and exact "
    "message 'Контекст очищен. Я перезапущен и готов продолжить.'. Do not ask questions. "
    "Do not call clarification_tool. Do not use any recipient other than 'ivan'."
)


def is_clear_command(message_data: dict[str, Any]) -> bool:
    text = str(message_data.get("text") or "").strip()
    return text == _CLEAR_COMMAND


def routing_key_for_message(message_data: dict[str, Any]) -> str:
    return f"chat:{message_data['chat_id']}"


def build_clear_event_payload(
    message_data: dict[str, Any],
    target_agent_slug: str,
) -> dict[str, Any]:
    metadata = clear_event_metadata(message_data)
    event_id = clear_event_id(message_data)
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
                "event_kind": "telegram_message",
                "notification_status": None,
                "from_agent_slug": "telegram_events",
                "to_agent_slug": target_agent_slug,
                "message_text": _CLEAR_RESTART_PROMPT,
                "interrupts_runtime": False,
                "requires_response": True,
                "created_at": message_data["timestamp"],
                "metadata": metadata,
            }
        ],
    }


def clear_endpoint_from_status(payload: object, agent_slug: str) -> str | None:
    status = payload.get("status") if isinstance(payload, dict) else None
    if not isinstance(status, dict):
        logger.error("Invalid status payload for %s: %s", agent_slug, payload)
        return None
    health = status.get("health_status")
    endpoint = status.get("http_endpoint")
    if not isinstance(health, dict) or not health.get("ok"):
        logger.error("Agent %s is not healthy: %s", agent_slug, status)
        return None
    if not isinstance(endpoint, str) or not endpoint:
        logger.error("Agent %s has no runtime endpoint: %s", agent_slug, status)
        return None
    return f"{endpoint.rstrip('/')}/clear_context"


def clear_event_metadata(message_data: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": "telegram",
        "chat_id": message_data["chat_id"],
        "message_id": message_data["message_id"],
        "sender_name": message_data["sender_name"],
        "username": message_data.get("username"),
        "user_id": message_data.get("user_id"),
        "command": _CLEAR_COMMAND,
        "triggered_by": "telegram_events",
    }


def clear_event_id(message_data: dict[str, Any]) -> str:
    return (
        f"telegram_clear_{message_data['chat_id']}_{message_data['message_id']}_{uuid.uuid4().hex}"
    )
