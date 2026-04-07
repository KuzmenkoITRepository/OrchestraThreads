from __future__ import annotations

import asyncio
from typing import Protocol

from core.orchestra_thread.client import OrchestraThreadsClient

_HEARTBEAT_INTERVAL_SECONDS = 15.0


class _RegistrationBackend(Protocol):
    http_endpoint: str | None
    config: dict[str, object]
    agent_slug: str
    backend_type: str
    _threads_client: OrchestraThreadsClient | None
    _heartbeat_task: asyncio.Task[None] | None


async def register_with_threads(backend: _RegistrationBackend) -> None:
    http_endpoint = backend.http_endpoint
    if not http_endpoint:
        return
    config = backend.config
    threads_url = str(config.get("threads_url") or "").strip() or "http://orchestra-threads:8788"
    client = OrchestraThreadsClient(base_url=threads_url)
    await client.register_agent(
        agent_slug=backend.agent_slug,
        display_name=backend.agent_slug,
        base_url=http_endpoint,
        metadata={
            "kind": "opencode-omo-agent",
            "backend_type": backend.backend_type,
            "tool_surface": "orchestra-threads-mcp",
        },
    )
    backend._threads_client = client
    backend._heartbeat_task = asyncio.create_task(_heartbeat_loop(backend))


async def stop_registration(backend: _RegistrationBackend) -> None:
    heartbeat_task = backend._heartbeat_task
    if heartbeat_task is not None:
        backend._heartbeat_task = None
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass  # noqa: WPS420
    threads_client = backend._threads_client
    if threads_client is not None:
        await threads_client.close()
        backend._threads_client = None


async def _heartbeat_loop(backend: _RegistrationBackend) -> None:
    while True:
        await asyncio.sleep(_HEARTBEAT_INTERVAL_SECONDS)
        threads_client = backend._threads_client
        if threads_client is None:
            return
        await threads_client.heartbeat(agent_slug=backend.agent_slug)
