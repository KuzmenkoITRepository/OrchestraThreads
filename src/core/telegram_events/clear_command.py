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

_KEY_CHAT_ID = "chat_id"
_KEY_MESSAGE_ID = "message_id"
_KEY_SENDER_NAME = "sender_name"
_KEY_TIMESTAMP = "timestamp"
_KEY_USERNAME = "username"
_KEY_USER_ID = "user_id"
_KEY_DELIVERY_ID = "delivery_id"
_KEY_EVENTS = "events"
_KEY_EVENT_ID = "event_id"
_KEY_THREAD_ID = "thread_id"
_KEY_ROOT_THREAD_ID = "root_thread_id"
_KEY_PARENT_THREAD_ID = "parent_thread_id"
_KEY_OWNER_AGENT_SLUG = "owner_agent_slug"
_KEY_SEQUENCE_NO = "sequence_no"
_KEY_EVENT_KIND = "event_kind"
_KEY_NOTIFICATION_STATUS = "notification_status"
_KEY_FROM_AGENT_SLUG = "from_agent_slug"
_KEY_TO_AGENT_SLUG = "to_agent_slug"
_KEY_MESSAGE_TEXT = "message_text"
_KEY_INTERRUPTS_RUNTIME = "interrupts_runtime"
_KEY_REQUIRES_RESPONSE = "requires_response"
_KEY_CREATED_AT = "created_at"
_KEY_METADATA = "metadata"
_KEY_SOURCE = "source"
_KEY_COMMAND = "command"
_KEY_TRIGGERED_BY = "triggered_by"
_KEY_REQUESTED_BY = "requested_by"
_KEY_ROUTING_KEY = "routing_key"
_KEY_CHAT_PREFIX = "chat:"
_KEY_TELEGRAM = "telegram"
_KEY_TELEGRAM_EVENTS = "telegram_events"
_KEY_TELEGRAM_MESSAGE = "telegram_message"
_KEY_CLEAR_CONTEXT = "telegram_events:/clear"


def is_clear_command(message_data: dict[str, Any]) -> bool:
    text = str(message_data.get("text") or "").strip()
    return text == _CLEAR_COMMAND


def routing_key_for_message(message_data: dict[str, Any]) -> str:
    chat_id = message_data[_KEY_CHAT_ID]
    return f"{_KEY_CHAT_PREFIX}{chat_id}"


def build_clear_event_payload(
    message_data: dict[str, Any],
    target_agent_slug: str,
) -> dict[str, Any]:
    metadata = clear_event_metadata(message_data)
    event_id = clear_event_id(message_data)
    return {
        _KEY_DELIVERY_ID: event_id,
        _KEY_EVENTS: [
            {
                _KEY_EVENT_ID: event_id,
                _KEY_THREAD_ID: None,
                _KEY_ROOT_THREAD_ID: None,
                _KEY_PARENT_THREAD_ID: None,
                _KEY_OWNER_AGENT_SLUG: None,
                _KEY_SEQUENCE_NO: None,
                _KEY_EVENT_KIND: _KEY_TELEGRAM_MESSAGE,
                _KEY_NOTIFICATION_STATUS: None,
                _KEY_FROM_AGENT_SLUG: _KEY_TELEGRAM_EVENTS,
                _KEY_TO_AGENT_SLUG: target_agent_slug,
                _KEY_MESSAGE_TEXT: _CLEAR_RESTART_PROMPT,
                _KEY_INTERRUPTS_RUNTIME: False,
                _KEY_REQUIRES_RESPONSE: True,
                _KEY_CREATED_AT: message_data[_KEY_TIMESTAMP],
                _KEY_METADATA: metadata,
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
    chat_id = message_data[_KEY_CHAT_ID]
    message_id = message_data[_KEY_MESSAGE_ID]
    sender_name = message_data[_KEY_SENDER_NAME]
    return {
        _KEY_SOURCE: _KEY_TELEGRAM,
        _KEY_CHAT_ID: chat_id,
        _KEY_MESSAGE_ID: message_id,
        _KEY_SENDER_NAME: sender_name,
        _KEY_USERNAME: message_data.get(_KEY_USERNAME),
        _KEY_USER_ID: message_data.get(_KEY_USER_ID),
        _KEY_COMMAND: _CLEAR_COMMAND,
        _KEY_TRIGGERED_BY: _KEY_TELEGRAM_EVENTS,
    }


def clear_event_id(message_data: dict[str, Any]) -> str:
    chat_id = message_data[_KEY_CHAT_ID]
    message_id = message_data[_KEY_MESSAGE_ID]
    return f"telegram_clear_{chat_id}_{message_id}_{uuid.uuid4().hex}"
