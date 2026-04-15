"""Message data extraction and formatting for Telegram events."""

from __future__ import annotations

import logging
from typing import Any

from core.telegram_events import clear_command
from core.telegram_events import service_event_payload as _event_payload

logger = logging.getLogger(__name__)


def extract_message_data(
    sse_event_update: dict[str, Any], occurred_at: str
) -> dict[str, Any] | None:
    """Extract message data from SSE update payload."""
    update = sse_event_update
    if "update" not in update and "message" not in update:
        return None

    raw_update = update.get("update", update)
    return _build_message_dict(raw_update, occurred_at)


def _build_message_dict(
    raw_update: dict[str, Any],
    occurred_at: str,
) -> dict[str, Any] | None:
    """Build message dict from raw update."""
    try:
        return _parse_message_fields(raw_update, occurred_at)
    except (KeyError, TypeError) as exc:
        logger.warning("Failed to extract message data: %s", exc)
        return None


def _parse_message_fields(raw_update: dict[str, Any], occurred_at: str) -> dict[str, Any]:
    """Parse individual message fields."""
    message = raw_update.get("message", {})
    sender = message.get("from", {})
    chat = message.get("chat", {})
    return {
        "message_id": message.get("id"),
        "sender_id": sender.get("id"),
        "sender_name": sender.get("first_name", "Unknown"),
        "chat_id": chat.get("id"),
        "chat_name": chat.get("title", "Private Chat"),
        "text": message.get("text", ""),
        "timestamp": message.get("date", occurred_at),
    }


def build_message_delivery(
    message_data: dict[str, Any],
    events_engine_url: str,
    resolved_agent_slug: str,
) -> tuple[str, dict[str, Any]]:
    """Build delivery payload for a message event."""
    event_data = _event_payload.build_message_event_payload(message_data, resolved_agent_slug)
    delivery_payload = _event_payload.build_delivery_payload(resolved_agent_slug, event_data)
    deliver_endpoint = f"{events_engine_url}/deliver"
    logger.info("Forwarding message to events-engine: %s", deliver_endpoint)
    logger.debug("Delivery payload: %s", delivery_payload)
    return deliver_endpoint, delivery_payload


def build_thread_message_text(message_data: dict[str, Any]) -> str:
    return _event_payload._message_prompt(message_data)  # noqa: WPS437


def message_client_request_id(message_data: dict[str, Any]) -> str:
    return _event_payload._message_event_id(message_data)  # noqa: WPS437


def build_clear_delivery(
    message_data: dict[str, Any],
    events_engine_url: str,
    resolved_agent_slug: str,
    orchestra_agents_url: str,
) -> tuple[str, dict[str, Any]] | None:
    """Build delivery payload for clear command."""
    if not orchestra_agents_url.rstrip("/"):
        return None
    event_data = clear_command.build_clear_event_payload(message_data, resolved_agent_slug)
    delivery_payload = _event_payload.build_delivery_payload(resolved_agent_slug, event_data)
    deliver_endpoint = f"{events_engine_url}/deliver"
    return deliver_endpoint, delivery_payload
