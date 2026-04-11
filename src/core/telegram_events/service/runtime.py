from __future__ import annotations

import asyncio
from typing import Any

import httpx
from aiohttp import web

from core.telegram_events import clear_command as _clear
from core.telegram_events import service_agent_api as _agent_api
from core.telegram_events import service_delivery as _delivery
from core.telegram_events import service_event_payload as _event_payload
from core.telegram_events.listener import TelegramListener
from core.telegram_events.service.support import (
    clear_proxy_env,
    listener_task,
    log_startup,
    resolve_forwarding_config,
    start_http_server,
    wait_for_shutdown,
)
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
        session_string = options.get("session_string")
        session_file = options.get("session_file")
        self._http_host = str(options.get("http_host", "0.0.0.0"))
        self._http_port = int(options.get("http_port", 8787))
        config = resolve_forwarding_config(options)
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
        log_startup(
            self.events_engine_url,
            self.target_agent_slug,
            self._http_host,
            self._http_port,
        )
        clear_proxy_env()
        self._shutdown_future = asyncio.get_running_loop().create_future()
        self.http_client = httpx.AsyncClient(timeout=30.0, trust_env=False)
        client = await self.listener.start_client()
        self.http_runner = await start_http_server(client, self._http_host, self._http_port)
        logger.info("HTTP server started")
        logger.info("Telegram listener started and waiting for messages...")
        if self._shutdown_future is None:
            raise RuntimeError("Shutdown future not initialized")
        await wait_for_shutdown(listener_task(client), self._shutdown_future)

    async def stop(self) -> None:
        """Stop the service."""
        logger.info("Stopping Telegram events service...")
        await _stop_http_runner(self)
        _resolve_shutdown_future(self._shutdown_future)
        await self.listener.stop()
        await _close_http_client(self.http_client)

    async def _forward_to_events_engine(self, message_data: dict[str, Any]) -> None:
        """Forward message to events-engine for delivery."""
        if _clear.is_clear_command(message_data):
            await self._handle_clear_command(message_data)
            return
        event_data = self._format_event_payload(message_data)
        delivery_payload = _event_payload.build_delivery_payload(self.target_agent_slug, event_data)
        endpoint = f"{self.events_engine_url}/deliver"
        logger.info("Forwarding message to events-engine: %s", endpoint)
        logger.debug("Delivery payload: %s", delivery_payload)
        await _delivery.forward_delivery(
            self.http_client,
            endpoint,
            delivery_payload,
            message_data,
        )

    async def _handle_clear_command(self, message_data: dict[str, Any]) -> None:
        routing_key = _clear.routing_key_for_message(message_data)
        endpoint = await _agent_api.resolve_clear_endpoint(
            client=self.http_client,
            orchestra_agents_url=self.orchestra_agents_url,
            agent_slug=self.target_agent_slug,
        )
        if endpoint is None:
            return
        if not await _agent_api.clear_agent_context(self.http_client, endpoint, routing_key):
            return
        event_data = _clear.build_clear_event_payload(message_data, self.target_agent_slug)
        delivery_payload = _event_payload.build_delivery_payload(self.target_agent_slug, event_data)
        deliver_endpoint = f"{self.events_engine_url}/deliver"
        logger.info("Forwarding synthetic clear event to events-engine: %s", deliver_endpoint)
        logger.debug("Synthetic clear delivery payload: %s", delivery_payload)
        await _delivery.forward_delivery(
            self.http_client,
            deliver_endpoint,
            delivery_payload,
            message_data,
        )

    def _format_event_payload(self, message_data: dict[str, Any]) -> dict[str, Any]:
        """Format message data into EventDelivery contract format."""
        return _event_payload.build_message_event_payload(message_data)


async def _stop_http_runner(service: TelegramEventsService) -> None:
    runner = service.http_runner
    if runner is None:
        return
    await runner.cleanup()
    service.http_runner = None


def _resolve_shutdown_future(shutdown_future: asyncio.Future[None] | None) -> None:
    if shutdown_future is None or shutdown_future.done():
        return
    shutdown_future.set_result(None)


async def _close_http_client(client: httpx.AsyncClient | None) -> None:
    if client is None:
        return
    await client.aclose()
