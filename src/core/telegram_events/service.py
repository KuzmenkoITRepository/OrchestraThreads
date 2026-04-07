"""Telegram events service main implementation."""

import asyncio
from typing import Any

import httpx
from aiohttp import web

from core.telegram_events import clear_command as _clear
from core.telegram_events import service_support as _support
from core.telegram_events.listener import TelegramListener
from core.telegram_events.service_logging import logger

_ORCHESTRA_AGENTS_URL = "http://orchestra-agents:8790"


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
        self._http_host = str(options.get("http_host", "0.0.0.0"))
        self._http_port = int(options.get("http_port", 8787))
        config = _support.resolve_forwarding_config(options)
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
        self.http_runner: web.AppRunner | None = None
        self._shutdown_future: asyncio.Future[None] | None = None
        self.orchestra_agents_url = str(
            options.get("orchestra_agents_url", _ORCHESTRA_AGENTS_URL)
        ).rstrip("/")

    async def start(self) -> None:
        """Start the service."""
        _support.log_startup(
            self.events_engine_url, self.target_agent_slug, self._http_host, self._http_port
        )
        _support.clear_proxy_env()
        self._shutdown_future = asyncio.get_running_loop().create_future()
        self.http_client = httpx.AsyncClient(timeout=30.0, trust_env=False)
        client = await self.listener.start_client()
        self.http_runner = await _support.start_http_server(
            client, self._http_host, self._http_port
        )
        logger.info("HTTP server started")
        logger.info("Telegram listener started and waiting for messages...")
        if self._shutdown_future is None:
            raise RuntimeError("Shutdown future not initialized")
        await _support.wait_for_shutdown(
            _support.listener_task(client),
            self._shutdown_future,
        )

    async def stop(self) -> None:
        """Stop the service."""
        logger.info("Stopping Telegram events service...")
        runner = self.http_runner
        if runner is not None:
            await runner.cleanup()
            self.http_runner = None
        shutdown_future = self._shutdown_future
        if shutdown_future is not None and not shutdown_future.done():
            shutdown_future.set_result(None)
        await self.listener.stop()
        if self.http_client:
            await self.http_client.aclose()

    async def _forward_to_events_engine(self, message_data: dict[str, Any]) -> None:
        """Forward message to events-engine for delivery."""
        if _clear.is_clear_command(message_data):
            await self._handle_clear_command(message_data)
            return
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
        _log_delivery_response(response, message_data)

    async def _handle_clear_command(self, message_data: dict[str, Any]) -> None:
        routing_key = _clear.routing_key_for_message(message_data)
        endpoint = await _resolve_clear_endpoint(
            client=self.http_client,
            orchestra_agents_url=self.orchestra_agents_url,
            agent_slug=self.target_agent_slug,
        )
        if endpoint is None:
            return
        if not await _clear_agent_context(self.http_client, endpoint, routing_key):
            return
        event_data = _clear.build_clear_event_payload(message_data, self.target_agent_slug)
        delivery_payload = {
            "agent_slug": self.target_agent_slug,
            "event_data": event_data,
        }
        deliver_endpoint = f"{self.events_engine_url}/deliver"
        logger.info("Forwarding synthetic clear event to events-engine: %s", deliver_endpoint)
        logger.debug("Synthetic clear delivery payload: %s", delivery_payload)
        await self._send_forward_request(deliver_endpoint, delivery_payload, message_data)

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
                    "event_id": f"telegram_{message_data['chat_id']}_{message_data['message_id']}",
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
                    "metadata": _message_metadata(message_data),
                }
            ],
        }


def _message_metadata(message_data: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": "telegram",
        "chat_id": message_data["chat_id"],
        "message_id": message_data["message_id"],
        "sender_name": message_data["sender_name"],
        "username": message_data.get("username"),
        "user_id": message_data.get("user_id"),
    }


def _log_delivery_response(
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


async def _resolve_clear_endpoint(
    *,
    client: httpx.AsyncClient | None,
    orchestra_agents_url: str,
    agent_slug: str,
) -> str | None:
    response = await _status_response(client, orchestra_agents_url, agent_slug)
    if response is None:
        logger.error("Failed to resolve clear_context endpoint for %s", agent_slug)
        return None
    return _clear.clear_endpoint_from_status(response.json(), agent_slug)


async def _status_response(
    client: httpx.AsyncClient | None,
    orchestra_agents_url: str,
    agent_slug: str,
) -> httpx.Response | None:
    if client is None:
        logger.error("HTTP client not initialized")
        return None
    status_url = f"{orchestra_agents_url}/api/v1/agents/{agent_slug}/status"
    try:
        response = await client.get(status_url)
    except Exception as exc:
        logger.error("Failed to fetch agent status for %s: %s", agent_slug, exc, exc_info=True)
        return None
    if response.status_code == 200:
        return response
    logger.error(
        "Agent status request failed for %s: status=%s body=%s",
        agent_slug,
        response.status_code,
        response.text,
    )
    return None


async def _clear_agent_context(
    client: httpx.AsyncClient | None,
    endpoint: str,
    routing_key: str,
) -> bool:
    if client is None:
        logger.error("HTTP client not initialized")
        return False
    payload = {
        "requested_by": "telegram_events:/clear",
        "routing_key": routing_key,
    }
    try:
        response = await client.post(endpoint, json=payload)
    except Exception as exc:
        logger.error("Failed to clear context via %s: %s", endpoint, exc, exc_info=True)
        return False
    if response.status_code == 200:
        logger.info("Cleared context for routing_key=%s", routing_key)
        return True
    logger.error(
        "Failed to clear context via %s: status=%s body=%s",
        endpoint,
        response.status_code,
        response.text,
    )
    return False
