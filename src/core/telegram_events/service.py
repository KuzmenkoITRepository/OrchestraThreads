"""Telegram events service main implementation."""

import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx

from core.telegram_events.listener import TelegramListener

logger = logging.getLogger(__name__)

_PROXY_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "http_proxy",
    "https_proxy",
    "ALL_PROXY",
    "all_proxy",
    "NO_PROXY",
    "no_proxy",
)


@dataclass(frozen=True)
class _ForwardingConfig:
    events_engine_url: str = "http://events-engine:8789"
    target_agent_slug: str = "secretary"


def _resolve_forwarding_config(options: dict[str, Any]) -> _ForwardingConfig:
    return _ForwardingConfig(
        events_engine_url=str(options.get("events_engine_url", "http://events-engine:8789")),
        target_agent_slug=str(options.get("target_agent_slug", "secretary")),
    )


class TelegramEventsService:
    """Service that listens to Telegram and forwards events to events-engine."""

    def __init__(
        self,
        api_id: int,
        api_hash: str,
        **options: Any,
    ) -> None:
        """
        Initialize Telegram events service.

        Args:
            api_id: Telegram API ID
            api_hash: Telegram API Hash
            session_string: Optional session string
            session_file: Optional session file path
            events_engine_url: Events engine HTTP endpoint
            target_agent_slug: Target agent slug for event delivery
        """
        session_string = options.get("session_string")
        session_file = options.get("session_file")
        config = _resolve_forwarding_config(options)
        self.events_engine_url = config.events_engine_url
        self.target_agent_slug = config.target_agent_slug
        self.listener = TelegramListener(
            api_id=api_id,
            api_hash=api_hash,
            session_string=session_string,
            session_file=session_file,
            on_message=self._forward_to_events_engine,
        )
        self.http_client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        """Start the service."""
        logger.info("Starting Telegram events service...")
        logger.info("Events engine endpoint: %s", self.events_engine_url)
        logger.info("Target agent: %s", self.target_agent_slug)
        for key in _PROXY_KEYS:
            os.environ.pop(key, None)
        self.http_client = httpx.AsyncClient(timeout=30.0, trust_env=False)
        await self.listener.start()

    async def stop(self) -> None:
        """Stop the service."""
        logger.info("Stopping Telegram events service...")
        await self.listener.stop()
        if self.http_client:
            await self.http_client.aclose()

    async def _forward_to_events_engine(self, message_data: dict[str, Any]) -> None:
        """Forward message to events-engine for delivery."""
        event_data = self._format_event_payload(message_data)
        delivery_payload = {
            "agent_slug": self.target_agent_slug,
            "event_data": event_data,
        }
        endpoint = f"{self.events_engine_url}/deliver"
        logger.info("Forwarding message to events-engine: %s", endpoint)
        logger.debug("Delivery payload: %s", delivery_payload)
        await self._send_forward_request(endpoint, delivery_payload, message_data)

    async def _send_forward_request(
        self,
        endpoint: str,
        delivery_payload: dict[str, Any],
        message_data: dict[str, Any],
    ) -> None:
        client = self.http_client
        if client is None:
            logger.error("HTTP client not initialized")
            return
        try:
            response = await client.post(endpoint, json=delivery_payload)
        except Exception as exc:
            logger.error("Error forwarding message to events-engine: %s", exc, exc_info=True)
            return
        self._log_delivery_response(response, message_data)

    def _log_delivery_response(
        self,
        response: httpx.Response,
        message_data: dict[str, Any],
    ) -> None:
        if response.status_code == 200:
            logger.info(
                "Successfully forwarded message %s to events-engine",
                message_data.get("message_id"),
            )
            return
        logger.error(
            "Failed to forward message to events-engine: status=%s, body=%s",
            response.status_code,
            response.text,
        )

    def _format_event_payload(self, message_data: dict[str, Any]) -> dict[str, Any]:
        """Format message data into EventDelivery contract format."""
        prompt_parts = [
            "New Telegram message received:",
            f"From: {message_data['sender_name']}",
        ]

        if message_data.get("username"):
            prompt_parts.append(f"Username: @{message_data['username']}")

        prompt_parts.extend(
            [
                f"Chat: {message_data['chat_name']}",
                f"Time: {message_data['timestamp']}",
                "",
                "Message:",
                message_data["text"],
            ]
        )

        prompt = "\n".join(prompt_parts)

        return {
            "delivery_id": f"telegram_{message_data['chat_id']}_{message_data['message_id']}",
            "events": [
                {
                    "event_id": None,
                    "thread_id": None,
                    "root_thread_id": None,
                    "parent_thread_id": None,
                    "owner_agent_slug": None,
                    "sequence_no": None,
                    "event_kind": "telegram_message",
                    "notification_status": None,
                    "from_agent_slug": "telegram_events",
                    "to_agent_slug": "secretary",
                    "message_text": prompt,
                    "interrupts_runtime": False,
                    "requires_response": True,
                    "created_at": message_data["timestamp"],
                    "metadata": {
                        "source": "telegram",
                        "chat_id": message_data["chat_id"],
                        "message_id": message_data["message_id"],
                        "sender_name": message_data["sender_name"],
                        "username": message_data.get("username"),
                        "user_id": message_data.get("user_id"),
                    },
                }
            ],
        }
