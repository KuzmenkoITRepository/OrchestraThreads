from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx
from aiohttp import web

from core.orchestra_thread.client import OrchestraThreadsClient
from core.telegram_events import sse_consumer
from core.telegram_events.service.support import start_http_server
from core.telegram_events.sse_event import SSEEvent


@dataclass(frozen=True)
class RuntimeResourceConfig:
    events_url: str
    bearer_token: str
    http_host: str
    http_port: int
    relay_url: str
    threads_url: str
    agent_slug: str


@dataclass(frozen=True)
class RuntimeResources:
    shutdown_future: asyncio.Future[None]
    http_client: httpx.AsyncClient
    threads_client: OrchestraThreadsClient
    consumer: sse_consumer.SSEConsumer
    http_runner: web.AppRunner
    heartbeat_task: asyncio.Task[None]


async def heartbeat_loop(client: OrchestraThreadsClient, *, agent_slug: str) -> None:
    while True:
        await asyncio.sleep(15.0)
        await client.heartbeat(agent_slug=agent_slug)


async def start_runtime_resources(
    *,
    config: RuntimeResourceConfig,
    on_event: Callable[[SSEEvent], Awaitable[None]],
) -> RuntimeResources:
    http_client = httpx.AsyncClient(timeout=30.0, trust_env=False)
    threads_client = OrchestraThreadsClient(base_url=config.threads_url)
    consumer = sse_consumer.SSEConsumer(
        events_url=config.events_url,
        bearer_token=config.bearer_token,
        on_event=on_event,
    )
    await consumer.start()
    http_runner = await start_http_server(
        config.http_host,
        config.http_port,
        relay_url=config.relay_url,
        bearer_token=config.bearer_token,
    )
    heartbeat_task = asyncio.create_task(
        heartbeat_loop(threads_client, agent_slug=config.agent_slug),
        name=f"{config.agent_slug}-threads-heartbeat",
    )
    return RuntimeResources(
        shutdown_future=asyncio.get_running_loop().create_future(),
        http_client=http_client,
        threads_client=threads_client,
        consumer=consumer,
        http_runner=http_runner,
        heartbeat_task=heartbeat_task,
    )


async def stop_runtime(
    runner: web.AppRunner | None,
    shutdown_future: asyncio.Future[None] | None,
    heartbeat_task: asyncio.Task[None] | None,
) -> None:
    if runner is not None:
        await runner.cleanup()
    if shutdown_future is not None and not shutdown_future.done():
        shutdown_future.set_result(None)
    if heartbeat_task is None:
        return
    heartbeat_task.cancel()
    await asyncio.gather(heartbeat_task, return_exceptions=True)


async def close_runtime_clients(
    threads_client: OrchestraThreadsClient | None,
    http_client: httpx.AsyncClient | None,
    consumer: sse_consumer.SSEConsumer | None,
) -> None:
    if threads_client is not None:
        await threads_client.close()
    if consumer is not None:
        await consumer.stop()
    if http_client is not None:
        await http_client.aclose()
