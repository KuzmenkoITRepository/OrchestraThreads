from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx
from aiohttp import web

from core.orchestra_thread.client import OrchestraThreadsClient
from core.telegram_events import sse_consumer
from core.telegram_events.sse_event import SSEEvent


@dataclass(frozen=True)
class RuntimeResourceConfig:
    http_host: str
    http_port: int
    threads_url: str
    agent_registry: Any
    register_agent: Any


@dataclass(frozen=True)
class ConsumerConfig:
    agent_slug: str
    telegram_mcp_url: str
    events_url: str
    bearer_token: str
    on_event: Callable[[SSEEvent], Awaitable[None]]


@dataclass(frozen=True)
class RuntimeResources:
    shutdown_future: asyncio.Future[None]
    http_client: httpx.AsyncClient
    threads_client: OrchestraThreadsClient
    http_runner: web.AppRunner


@dataclass(frozen=True)
class ManagedConsumer:
    agent_slug: str
    telegram_mcp_url: str
    events_url: str
    consumer: sse_consumer.SSEConsumer
