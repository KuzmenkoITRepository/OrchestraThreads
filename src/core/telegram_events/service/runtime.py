"""Telegram events service runtime using SSE consumer."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

import httpx
from aiohttp import web

from core.telegram_events import (
    _runtime_message_handler,
    clear_command,
    service_agent_api,
    service_delivery,
)
from core.telegram_events import (
    service_runtime_binding_support as runtime_binding_support,
)
from core.telegram_events.agent_registry import RegistrationResult, TelegramAgentRegistry
from core.telegram_events.service import (
    runtime_models,
    runtime_registry_support,
    runtime_support,
)
from core.telegram_events.service.support import (
    clear_proxy_env,
    log_startup,
    resolve_forwarding_config,
    wait_for_shutdown,
)

if TYPE_CHECKING:
    from core.orchestra_thread.client import OrchestraThreadsClient


logger = logging.getLogger(__name__)

_ORCHESTRA_AGENTS_URL = "http://orchestra-agents:8790"
_ORCHESTRA_THREADS_URL = "http://orchestra-threads:8788"
_TELEGRAM_EVENTS_AGENT_SLUG = "telegram_events"


def _thread_message_text(message_data: dict[str, Any]) -> str:
    return _runtime_message_handler.build_thread_message_text(message_data)


def _client_request_id(message_data: dict[str, Any]) -> str:
    return _runtime_message_handler.message_client_request_id(message_data)


def _public_base_url(options: dict[str, Any]) -> str:
    return str(options.get("public_base_url", "")).strip().rstrip("/")


async def _prepare_runtime(service: TelegramEventsService) -> None:
    clear_proxy_env()
    runtime_resources = await runtime_support.start_runtime_resources(
        config=runtime_binding_support.runtime_resource_config(service),
    )
    runtime_binding_support.apply_runtime_resources(service, runtime_resources)
    await runtime_binding_support.register_with_threads(service)


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
        self._agent_slug = str(options.get("agent_slug", _TELEGRAM_EVENTS_AGENT_SLUG)).strip()
        self._bearer_token = str(options.get("bearer_token", ""))
        self._agent_registry = TelegramAgentRegistry()
        self._agent_registry_lock = asyncio.Lock()
        self._consumers_by_mcp_url: dict[str, runtime_models.ManagedConsumer] = {}
        self._http_client: httpx.AsyncClient | None = None
        self._http_runner: web.AppRunner | None = None
        self._shutdown_future: asyncio.Future[None] | None = None
        self._orchestra_agents_url = str(
            options.get("orchestra_agents_url", _ORCHESTRA_AGENTS_URL)
        ).rstrip("/")
        self._threads_url = str(options.get("threads_url", _ORCHESTRA_THREADS_URL)).rstrip("/")
        self._public_base_url = _public_base_url(options)
        self._threads_client: OrchestraThreadsClient | None = None
        self._thread_registry = _TelegramThreadRegistry()
        self._heartbeat_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the service."""
        log_startup(
            self._events_engine_url,
            self._http_host,
            self._http_port,
        )
        await _prepare_runtime(self)
        logger.info("HTTP server started")
        logger.info("Runtime ready for dynamic SSE registrations")
        await wait_for_shutdown(
            runtime_registry_support.require_shutdown_future(self._shutdown_future)
        )

    async def stop(self) -> None:
        """Stop the service."""
        logger.info("Stopping Telegram events service...")
        await runtime_support.stop_runtime(
            self._http_runner,
            self._shutdown_future,
            self._heartbeat_task,
        )
        await runtime_support.stop_consumers(tuple(self._consumers_by_mcp_url.values()))
        self._consumers_by_mcp_url.clear()
        await runtime_support.close_runtime_clients(self._threads_client, self._http_client)

    async def register_agent(
        self,
        _agent_registry: object,
        agent_slug: str,
        telegram_mcp_url: str,
    ) -> RegistrationResult:
        result = await runtime_registry_support.register_runtime_consumer(
            self,
            agent_slug,
            telegram_mcp_url,
        )
        logger.info(
            "Registration %s for %s via %s",
            result.status,
            result.agent_slug,
            result.telegram_mcp_url,
        )
        return result

    async def _handle_sse_event(
        self,
        sse_event: Any,
        source_telegram_mcp_url: str | None = None,
    ) -> None:
        """Handle incoming SSE event and forward to events-engine."""
        if sse_event.event_type not in ("message", "new_message"):
            logger.debug("Skipping non-message event: %s", sse_event.event_type)
            return

        message_data = _runtime_message_handler.extract_message_data(
            sse_event.update, sse_event.occurred_at
        )
        if not message_data:
            return

        target_agent_slug = runtime_registry_support.resolve_target_slug(
            self,
            source_telegram_mcp_url,
        )
        if target_agent_slug is None:
            return

        if clear_command.is_clear_command(message_data):
            await self._forward_clear_event(message_data, target_agent_slug)
            return

        await self._forward_message_event(message_data, target_agent_slug)

    async def _forward_message_event(
        self,
        message_data: dict[str, Any],
        target_agent_slug: str,
    ) -> None:
        """Forward a normal message through orchestra-thread ingress."""
        threads_client = runtime_binding_support.require_threads_client(self._threads_client)
        chat_id = message_data.get("chat_id")
        response = await threads_client.send_message(
            from_agent_slug=self._agent_slug,
            to_agent_slug=target_agent_slug,
            message_text=_thread_message_text(message_data),
            thread_id=self._thread_registry.get(chat_id),
            parent_thread_id=None,
            client_request_id=_client_request_id(message_data),
        )
        thread_id = runtime_binding_support.extract_thread_id(response)
        self._thread_registry.set(chat_id, thread_id)

    async def _forward_clear_event(
        self,
        message_data: dict[str, Any],
        target_agent_slug: str,
    ) -> None:
        """Forward a clear command event to events-engine."""
        routing_key = clear_command.routing_key_for_message(message_data)
        endpoint = await service_agent_api.resolve_clear_endpoint(
            client=self._http_client,
            orchestra_agents_url=self._orchestra_agents_url,
            agent_slug=target_agent_slug,
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
            target_agent_slug,
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
