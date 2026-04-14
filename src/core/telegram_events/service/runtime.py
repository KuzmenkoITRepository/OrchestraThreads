"""Telegram events service runtime using SSE consumer."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from aiohttp import web

from core.orchestra_thread.client import OrchestraThreadsClient
from core.telegram_events import (
    _runtime_message_handler,
    clear_command,
    service_agent_api,
    service_delivery,
    sse_consumer,
    sse_event,
)  # noqa: WPS201  # Consolidated to reduce import count
from core.telegram_events import (
    service_runtime_binding_support as runtime_binding_support,
)
from core.telegram_events.service.runtime_support import (
    close_runtime_clients,
    start_runtime_resources,
    stop_runtime,
)
from core.telegram_events.service.support import (
    clear_proxy_env,
    log_startup,
    resolve_forwarding_config,
    wait_for_shutdown,
)

logger = logging.getLogger(__name__)

_ORCHESTRA_AGENTS_URL = "http://orchestra-agents:8790"
_ORCHESTRA_THREADS_URL = "http://orchestra-threads:8788"
_TELEGRAM_EVENTS_AGENT_SLUG = "telegram_events"


def _log_runtime_targets(service: TelegramEventsService) -> None:
    logger.info("MCP URL: %s", service._mcp_url)
    logger.info("SSE events URL: %s", service._events_url)


async def _prepare_runtime(service: TelegramEventsService) -> None:
    clear_proxy_env()
    runtime_resources = await start_runtime_resources(
        config=runtime_binding_support.runtime_resource_config(service),
        on_event=service._handle_sse_event,
    )
    runtime_binding_support.apply_runtime_resources(service, runtime_resources)
    await service._register_with_threads()


def _require_shutdown_future(shutdown_future: asyncio.Future[None] | None) -> asyncio.Future[None]:
    if shutdown_future is None:
        raise RuntimeError("Shutdown future not initialized")
    return shutdown_future


class _TelegramThreadRegistry:
    def __init__(self) -> None:
        self._threads_by_chat: dict[str, str] = {}

    def get(self, chat_id: object) -> str | None:
        return self._threads_by_chat.get(self._chat_key(chat_id))

    def set(self, chat_id: object, thread_id: str) -> None:
        self._threads_by_chat[self._chat_key(chat_id)] = thread_id

    def reset(self, chat_id: object) -> None:
        self._threads_by_chat.pop(self._chat_key(chat_id), None)

    @staticmethod
    def _chat_key(chat_id: object) -> str:
        return str(chat_id).strip()


class TelegramEventsService:
    """Service that consumes Telegram events via SSE and forwards to events-engine."""

    def __init__(self, **options: Any) -> None:
        self._http_host = str(options.get("http_host", "0.0.0.0"))
        self._http_port = int(options.get("http_port", 8787))
        config = resolve_forwarding_config(options)
        self._events_engine_url = config.events_engine_url
        self._target_agent_slug = config.target_agent_slug
        self._agent_slug = str(options.get("agent_slug", _TELEGRAM_EVENTS_AGENT_SLUG)).strip()
        self._mcp_url = str(
            options.get(
                "mcp_url",
                "http://better-telegram-mcp:3000/mcp",
            )
        )
        self._events_url = str(
            options.get(
                "events_url",
                "http://better-telegram-mcp:3000/events/telegram",
            )
        )
        self._bearer_token = str(options.get("bearer_token", ""))
        self._consumer: sse_consumer.SSEConsumer | None = None
        self._http_client: httpx.AsyncClient | None = None
        self._http_runner: web.AppRunner | None = None
        self._shutdown_future: asyncio.Future[None] | None = None
        self._orchestra_agents_url = str(
            options.get("orchestra_agents_url", _ORCHESTRA_AGENTS_URL)
        ).rstrip("/")
        self._threads_url = str(options.get("threads_url", _ORCHESTRA_THREADS_URL)).rstrip("/")
        self._public_base_url = runtime_binding_support.normalized_public_base_url(options)
        self._threads_client: OrchestraThreadsClient | None = None
        self._thread_registry = _TelegramThreadRegistry()
        self._heartbeat_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the service."""
        log_startup(
            self._events_engine_url,
            self._target_agent_slug,
            self._http_host,
            self._http_port,
        )
        _log_runtime_targets(self)
        await _prepare_runtime(self)
        logger.info("HTTP server started")
        logger.info("SSE consumer started and waiting for events...")
        await wait_for_shutdown(_require_shutdown_future(self._shutdown_future))

    async def stop(self) -> None:
        """Stop the service."""
        logger.info("Stopping Telegram events service...")
        await stop_runtime(self._http_runner, self._shutdown_future, self._heartbeat_task)
        await close_runtime_clients(self._threads_client, self._http_client, self._consumer)

    async def _handle_sse_event(self, sse_event: sse_event.SSEEvent) -> None:
        """Handle incoming SSE event and forward to events-engine."""
        if sse_event.event_type not in ("message", "new_message"):
            logger.debug("Skipping non-message event: %s", sse_event.event_type)
            return

        message_data = _runtime_message_handler.extract_message_data(
            sse_event.update, sse_event.occurred_at
        )
        if not message_data:
            return

        if clear_command.is_clear_command(message_data):
            await self._forward_clear_event(message_data)
            return

        await self._forward_message_event(message_data)

    async def _forward_message_event(self, message_data: dict[str, Any]) -> None:
        """Forward a normal message through orchestra-thread ingress."""
        threads_client = runtime_binding_support.require_threads_client(self._threads_client)
        response = await threads_client.send_message(
            from_agent_slug=self._agent_slug,
            to_agent_slug=self._target_agent_slug,
            message_text=_runtime_message_handler.build_thread_message_text(message_data),
            thread_id=self._thread_registry.get(message_data.get("chat_id")),
            parent_thread_id=None,
            client_request_id=_runtime_message_handler.message_client_request_id(message_data),
        )
        thread_id = runtime_binding_support.extract_thread_id(response)
        self._thread_registry.set(message_data.get("chat_id"), thread_id)

    async def _forward_clear_event(self, message_data: dict[str, Any]) -> None:
        """Forward a clear command event to events-engine."""
        routing_key = clear_command.routing_key_for_message(message_data)
        endpoint = await service_agent_api.resolve_clear_endpoint(
            client=self._http_client,
            orchestra_agents_url=self._orchestra_agents_url,
            agent_slug=self._target_agent_slug,
        )
        if endpoint is None:
            return
        if not await service_agent_api.clear_agent_context(
            self._http_client, endpoint, routing_key
        ):
            return
        self._thread_registry.reset(message_data.get("chat_id"))
        delivery = _runtime_message_handler.build_clear_delivery(
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
        await service_delivery.forward_delivery(
            self._http_client,
            deliver_endpoint,
            delivery_payload,
            message_data,
        )

    async def _register_with_threads(self) -> None:
        threads_client = runtime_binding_support.require_threads_client(self._threads_client)
        base_url = runtime_binding_support.registration_base_url(self)
        await threads_client.register_agent(
            agent_slug=self._agent_slug,
            display_name=self._agent_slug,
            base_url=base_url,
            metadata={
                "kind": "telegram-events-service",
                "backend_type": "telegram-events",
                "tool_surface": "telegram-events-ingress",
                "allowed_peer_agent_slugs": [self._target_agent_slug],
            },
        )
