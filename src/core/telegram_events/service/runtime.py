"""Telegram events service runtime using SSE consumer."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from aiohttp import web

from core.telegram_events import _runtime_message_handler as _msg_handler
from core.telegram_events import clear_command as _clear
from core.telegram_events import service_agent_api as _agent_api
from core.telegram_events import service_delivery as _delivery
from core.telegram_events.service.support import (
    clear_proxy_env,
    log_startup,
    resolve_forwarding_config,
    start_http_server,
    wait_for_shutdown,
)
from core.telegram_events.service_logging import logger
from core.telegram_events.sse_consumer import SSEConsumer, SSEEvent

_ORCHESTRA_AGENTS_URL = "http://orchestra-agents:8790"


class TelegramEventsService:
    """Service that consumes Telegram events via SSE and forwards to events-engine."""

    def __init__(self, **options: Any) -> None:
        self._http_host = str(options.get("http_host", "0.0.0.0"))
        self._http_port = int(options.get("http_port", 8787))
        config = resolve_forwarding_config(options)
        self._events_engine_url = config.events_engine_url
        self._target_agent_slug = config.target_agent_slug
        self._events_url = str(
            options.get(
                "events_url",
                "http://better-telegram-mcp:3000/events/telegram",
            )
        )
        self._bearer_token = str(options.get("bearer_token", ""))
        self._consumer: SSEConsumer | None = None
        self._http_client: httpx.AsyncClient | None = None
        self._http_runner: web.AppRunner | None = None
        self._shutdown_future: asyncio.Future[None] | None = None
        self._orchestra_agents_url = str(
            options.get("orchestra_agents_url", _ORCHESTRA_AGENTS_URL)
        ).rstrip("/")

    async def start(self) -> None:
        """Start the service."""
        log_startup(
            self._events_engine_url,
            self._target_agent_slug,
            self._http_host,
            self._http_port,
        )
        clear_proxy_env()
        self._shutdown_future = asyncio.get_running_loop().create_future()
        self._http_client = httpx.AsyncClient(timeout=30.0, trust_env=False)
        self._consumer = SSEConsumer(
            events_url=self._events_url,
            bearer_token=self._bearer_token,
            on_event=self._handle_sse_event,
        )
        await self._consumer.start()
        self._http_runner = await start_http_server(
            self._http_host,
            self._http_port,
            relay_url=self._events_url,
            bearer_token=self._bearer_token,
        )
        logger.info("HTTP server started")
        logger.info("SSE consumer started and waiting for events...")
        if self._shutdown_future is None:
            raise RuntimeError("Shutdown future not initialized")
        await wait_for_shutdown(self._shutdown_future)

    async def stop(self) -> None:
        """Stop the service."""
        logger.info("Stopping Telegram events service...")
        await _stop_http_runner(self._http_runner)
        _resolve_shutdown_future(self._shutdown_future)
        if self._consumer:
            await self._consumer.stop()
        await _close_http_client(self._http_client)

    async def _handle_sse_event(self, sse_event: SSEEvent) -> None:
        """Handle incoming SSE event and forward to events-engine."""
        if sse_event.event_type not in ("message", "new_message"):
            logger.debug("Skipping non-message event: %s", sse_event.event_type)
            return

        message_data = _msg_handler.extract_message_data(sse_event.update, sse_event.occurred_at)
        if not message_data:
            return

        if _clear.is_clear_command(message_data):
            await self._forward_clear_event(message_data)
            return

        await self._forward_message_event(message_data)

    async def _forward_message_event(self, message_data: dict[str, Any]) -> None:
        """Forward a normal message event to events-engine."""
        endpoint, payload = _msg_handler.build_message_delivery(
            message_data, self._events_engine_url, self._target_agent_slug
        )
        await _delivery.forward_delivery(
            self._http_client,
            endpoint,
            payload,
            message_data,
        )

    async def _forward_clear_event(self, message_data: dict[str, Any]) -> None:
        """Forward a clear command event to events-engine."""
        routing_key = _clear.routing_key_for_message(message_data)
        endpoint = await _agent_api.resolve_clear_endpoint(
            client=self._http_client,
            orchestra_agents_url=self._orchestra_agents_url,
            agent_slug=self._target_agent_slug,
        )
        if endpoint is None:
            return
        if not await _agent_api.clear_agent_context(self._http_client, endpoint, routing_key):
            return
        delivery = _msg_handler.build_clear_delivery(
            message_data,
            self._events_engine_url,
            self._target_agent_slug,
            self._orchestra_agents_url,
        )
        if delivery is None:
            return
        deliver_endpoint, delivery_payload = delivery
        logger.info(
            "Forwarding synthetic clear event to events-engine: %s",
            deliver_endpoint,
        )
        logger.debug("Synthetic clear delivery payload: %s", delivery_payload)
        await _delivery.forward_delivery(
            self._http_client,
            deliver_endpoint,
            delivery_payload,
            message_data,
        )


async def _stop_http_runner(runner: web.AppRunner | None) -> None:
    if runner is None:
        return
    await runner.cleanup()


def _resolve_shutdown_future(shutdown_future: asyncio.Future[None] | None) -> None:
    if shutdown_future is None or shutdown_future.done():
        return
    shutdown_future.set_result(None)


async def _close_http_client(client: httpx.AsyncClient | None) -> None:
    if client is None:
        return
    await client.aclose()
