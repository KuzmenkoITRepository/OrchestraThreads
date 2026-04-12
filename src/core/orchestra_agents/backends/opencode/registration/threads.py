from __future__ import annotations

import asyncio
import os
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
    config = backend.config
    threads_url = str(config.get("threads_url") or "").strip() or "http://orchestra-threads:8788"
    client = OrchestraThreadsClient(base_url=threads_url)
    await client.register_agent(
        agent_slug=backend.agent_slug,
        display_name=backend.agent_slug,
        base_url=backend.http_endpoint,
        metadata={
            "kind": "opencode-omo-agent",
            "backend_type": backend.backend_type,
            "tool_surface": "orchestra-threads-mcp",
            "allowed_peer_agent_slugs": _allowed_peers(),
        },
    )
    backend._threads_client = client
    backend._heartbeat_task = asyncio.create_task(_heartbeat_loop(backend))


async def stop_registration(backend: _RegistrationBackend) -> None:
    heartbeat_task = backend._heartbeat_task
    if heartbeat_task is not None:
        backend._heartbeat_task = None
        heartbeat_task.cancel()
        await asyncio.gather(heartbeat_task, return_exceptions=True)
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


def _allowed_peers() -> list[str]:
    raw = str(os.getenv("ORCHESTRA_AGENT_ALLOWED_PEER_AGENT_SLUGS") or "").strip()
    if not raw:
        return []
    peers: list[str] = []
    for item in raw.split(","):
        slug = item.strip()
        if slug:
            peers.append(slug)
    return peers
