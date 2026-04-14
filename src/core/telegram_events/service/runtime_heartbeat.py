from __future__ import annotations

import asyncio

from core.orchestra_thread.client import OrchestraThreadsClient

_HEARTBEAT_INTERVAL_SECONDS = 15.0


async def heartbeat_loop(client: OrchestraThreadsClient, *, agent_slug: str) -> None:
    while True:
        await asyncio.sleep(_HEARTBEAT_INTERVAL_SECONDS)
        await client.heartbeat(agent_slug=agent_slug)
