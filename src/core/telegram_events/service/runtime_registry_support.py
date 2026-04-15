from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from functools import partial
from typing import TYPE_CHECKING, cast

from core.telegram_events.agent_registry import AgentRegistration, RegistrationResult
from core.telegram_events.service.runtime_models import (
    ConsumerConfig,
    ManagedConsumer,
)
from core.telegram_events.service.runtime_support import (
    start_sse_consumer,
    stop_consumers,
)
from core.telegram_events.sse_event import SSEEvent

if TYPE_CHECKING:
    from core.telegram_events.service.runtime import TelegramEventsService


logger = logging.getLogger(__name__)


def consumer_config(
    service: TelegramEventsService,
    agent_slug: str,
    telegram_mcp_url: str,
    events_url: str,
) -> ConsumerConfig:
    on_event = cast(
        Callable[[SSEEvent], Awaitable[None]],
        partial(service._handle_sse_event, source_telegram_mcp_url=telegram_mcp_url),
    )
    return ConsumerConfig(
        agent_slug=agent_slug,
        telegram_mcp_url=telegram_mcp_url,
        events_url=events_url,
        bearer_token=service._bearer_token,
        on_event=on_event,
    )


def resolve_target_slug(
    service: TelegramEventsService,
    source_telegram_mcp_url: str | None,
) -> str | None:
    if source_telegram_mcp_url is None:
        logger.warning("Dropping SSE event without source MCP URL")
        return None
    target_agent_slug = service._agent_registry.get_slug_for_mcp_url(source_telegram_mcp_url)
    if target_agent_slug is None:
        logger.warning(
            "Dropping SSE event from unknown source MCP URL: %s",
            source_telegram_mcp_url,
        )
        return None
    return target_agent_slug


async def register_runtime_consumer(
    service: TelegramEventsService,
    agent_slug: str,
    telegram_mcp_url: str,
) -> RegistrationResult:
    consumer_to_stop: ManagedConsumer | None = None
    async with service._agent_registry_lock:
        existing_registration = service._agent_registry.get_registration_for_slug(agent_slug)
        result = service._agent_registry.register(agent_slug, telegram_mcp_url)
        if result.is_conflict or result.is_duplicate:
            return result
        try:
            started_consumer = await _build_consumer(service, result)
        except Exception:
            _rollback_registration(service, result, existing_registration)
            raise
        service._consumers_by_mcp_url[result.telegram_mcp_url] = started_consumer
        if result.previous_telegram_mcp_url is not None:
            consumer_to_stop = service._consumers_by_mcp_url.pop(
                result.previous_telegram_mcp_url,
                None,
            )
    await _stop_managed_consumer(consumer_to_stop)
    return result


def require_shutdown_future(
    shutdown_future: asyncio.Future[None] | None,
) -> asyncio.Future[None]:
    if shutdown_future is None:
        raise RuntimeError("Shutdown future not initialized")
    return shutdown_future


async def _build_consumer(
    service: TelegramEventsService,
    result: RegistrationResult,
) -> ManagedConsumer:
    return await start_sse_consumer(
        config=consumer_config(
            service,
            result.agent_slug,
            result.telegram_mcp_url,
            result.events_url,
        )
    )


def _rollback_registration(
    service: TelegramEventsService,
    result: RegistrationResult,
    existing_registration: AgentRegistration | None,
) -> None:
    service._agent_registry._by_slug.pop(result.agent_slug, None)
    service._agent_registry._by_mcp_url.pop(result.telegram_mcp_url, None)
    if existing_registration is None:
        return
    service._agent_registry._by_slug[result.agent_slug] = existing_registration
    service._agent_registry._by_mcp_url[existing_registration.telegram_mcp_url] = result.agent_slug


async def _stop_managed_consumer(consumer: ManagedConsumer | None) -> None:
    if consumer is None:
        return
    await stop_consumers((consumer,))
