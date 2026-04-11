"""Runtime assembly for events_engine."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from aiohttp import web
from aiohttp.client import ClientSession, ClientTimeout

from core.events_engine.service import delivery, http, support


class EventsEngine:
    """Routes events from external sources to agents via their /event endpoints."""

    def __init__(
        self,
        orchestra_agents_url: str = "http://orchestra-agents:8790",
    ) -> None:
        self.orchestra_agents_url = orchestra_agents_url
        self.http_session: ClientSession | None = None
        self.app: web.Application | None = None

    async def start(self) -> None:
        """Start the events engine service."""
        support.logger.info("Starting events engine service...")
        self.http_session = ClientSession(
            timeout=ClientTimeout(total=support.HTTP_SESSION_TIMEOUT_SECONDS)
        )

        self.app = web.Application()
        self.app.router.add_post("/deliver", self._handle_deliver)
        self.app.router.add_get("/healthz", http.healthz_handler)

        runner = web.AppRunner(self.app)
        await runner.setup()

        host = os.getenv("EVENTS_ENGINE_HOST", "0.0.0.0")
        port = int(os.getenv("EVENTS_ENGINE_PORT", "8789"))

        site = web.TCPSite(runner, host, port)
        await site.start()
        support.logger.info("Events engine listening on %s:%s", host, port)

        await asyncio.Event().wait()

    async def stop(self) -> None:
        """Stop the events engine service."""
        support.logger.info("Stopping events engine service...")
        if self.http_session:
            await self.http_session.close()

    async def _handle_deliver(self, request: web.Request) -> web.Response:
        return await http.handle_deliver(self, request)

    async def _get_agent_endpoint(self, agent_slug: str) -> str | None:
        return await delivery.get_agent_endpoint(
            http_session=self.http_session,
            orchestra_agents_url=self.orchestra_agents_url,
            agent_slug=agent_slug,
        )

    async def _deliver_to_agent(self, agent_endpoint: str, event_data: dict[str, Any]) -> bool:
        return await delivery.deliver_to_agent(
            http_session=self.http_session,
            agent_endpoint=agent_endpoint,
            event_data=event_data,
        )
