from __future__ import annotations

import asyncio
from collections.abc import Iterable

import httpx
from aiohttp import web

from core.orchestra_thread.client import OrchestraThreadsClient
from core.telegram_events import sse_consumer
from core.telegram_events.service.runtime_models import (
    ConsumerConfig,
    ManagedConsumer,
    RuntimeResourceConfig,
    RuntimeResources,
)
from core.telegram_events.service.support import start_http_server


async def start_runtime_resources(
    *,
    config: RuntimeResourceConfig,
) -> RuntimeResources:
    http_client = httpx.AsyncClient(timeout=30.0, trust_env=False)
    threads_client = OrchestraThreadsClient(base_url=config.threads_url)
    http_runner = await start_http_server(
        config.http_host,
        config.http_port,
        agent_registry=config.agent_registry,
        register_agent=config.register_agent,
    )
    heartbeat_task = asyncio.create_task(
        _heartbeat_loop(threads_client, agent_slug=config.agent_slug),
        name=f"{config.agent_slug}-threads-heartbeat",
    )
    return RuntimeResources(
        shutdown_future=asyncio.get_running_loop().create_future(),
        http_client=http_client,
        threads_client=threads_client,
        http_runner=http_runner,
        heartbeat_task=heartbeat_task,
    )


async def start_sse_consumer(*, config: ConsumerConfig) -> ManagedConsumer:
    consumer = sse_consumer.SSEConsumer(
        events_url=config.events_url,
        bearer_token=config.bearer_token,
        on_event=config.on_event,
    )
    await consumer.start()
    return ManagedConsumer(
        agent_slug=config.agent_slug,
        telegram_mcp_url=config.telegram_mcp_url,
        events_url=config.events_url,
        consumer=consumer,
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
) -> None:
    if threads_client is not None:
        await threads_client.close()
    if http_client is not None:
        await http_client.aclose()


async def stop_consumers(consumers: Iterable[ManagedConsumer]) -> None:
    await asyncio.gather(
        *(consumer.consumer.stop() for consumer in consumers),
        return_exceptions=True,
    )


async def _heartbeat_loop(client: OrchestraThreadsClient, *, agent_slug: str) -> None:
    while True:
        await asyncio.sleep(15.0)
        await client.heartbeat(agent_slug=agent_slug)
