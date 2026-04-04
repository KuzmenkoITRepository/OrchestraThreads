"""Telegram events service main implementation."""

import logging
import os
from typing import Optional

import httpx

from .listener import TelegramListener

logger = logging.getLogger(__name__)


class TelegramEventsService:
    """Service that listens to Telegram and forwards events to events-engine."""

    def __init__(
        self,
        api_id: int,
        api_hash: str,
        session_string: Optional[str] = None,
        session_file: Optional[str] = None,
        events_engine_url: str = "http://events-engine:8789",
        target_agent_slug: str = "secretary",
    ):
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
        self.events_engine_url = events_engine_url
        self.target_agent_slug = target_agent_slug
        self.listener = TelegramListener(
            api_id=api_id,
            api_hash=api_hash,
            session_string=session_string,
            session_file=session_file,
            on_message=self._forward_to_events_engine,
        )
        self.http_client: Optional[httpx.AsyncClient] = None

    async def start(self):
        """Start the service."""
        logger.info("Starting Telegram events service...")
        logger.info(f"Events engine endpoint: {self.events_engine_url}")
        logger.info(f"Target agent: {self.target_agent_slug}")

        for key in [
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "http_proxy",
            "https_proxy",
            "ALL_PROXY",
            "all_proxy",
            "NO_PROXY",
            "no_proxy",
        ]:
            os.environ.pop(key, None)

        self.http_client = httpx.AsyncClient(timeout=30.0, trust_env=False)

        await self.listener.start()

    async def stop(self):
        """Stop the service."""
        logger.info("Stopping Telegram events service...")

        if self.listener:
            await self.listener.stop()

        if self.http_client:
            await self.http_client.aclose()

    async def _forward_to_events_engine(self, message_data: dict):
        """Forward message to events-engine for delivery."""
        try:
            event_data = self._format_event_payload(message_data)

            delivery_payload = {
                "agent_slug": self.target_agent_slug,
                "event_data": event_data,
            }

            endpoint = f"{self.events_engine_url}/deliver"

            logger.info(f"Forwarding message to events-engine: {endpoint}")
            logger.debug(f"Delivery payload: {delivery_payload}")

            if not self.http_client:
                logger.error("HTTP client not initialized")
                return

            response = await self.http_client.post(
                endpoint,
                json=delivery_payload,
            )

            if response.status_code == 200:
                logger.info(
                    f"Successfully forwarded message {message_data['message_id']} to events-engine"
                )
            else:
                logger.error(
                    f"Failed to forward message to events-engine: "
                    f"status={response.status_code}, body={response.text}"
                )

        except Exception as e:
            logger.error(
                f"Error forwarding message to events-engine: {e}", exc_info=True
            )

    def _format_event_payload(self, message_data: dict) -> dict:
        """Format message data into EventDelivery contract format."""
        prompt_parts = [
            f"New Telegram message received:",
            f"From: {message_data['sender_name']}",
        ]

        if message_data.get("username"):
            prompt_parts.append(f"Username: @{message_data['username']}")

        prompt_parts.extend(
            [
                f"Chat: {message_data['chat_name']}",
                f"Time: {message_data['timestamp']}",
                f"",
                f"Message:",
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
                    "requires_response": False,
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
