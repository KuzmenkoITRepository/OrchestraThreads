"""Events engine service for routing events to agents."""

import asyncio
import os
from typing import Any

from aiohttp import web
from aiohttp.client import ClientSession, ClientTimeout

from core.events_engine import service_support as _support

logger = _support.logger


async def _healthz_handler(request: web.Request) -> web.Response:
    return web.json_response({"status": "healthy"})


async def _process_delivery(
    engine: "EventsEngine", payload: _support.DeliverPayload
) -> web.Response:
    agent_slug = payload["agent_slug"]
    event_data = payload["event_data"]
    logger.info("Delivering event to agent: %s", agent_slug)
    agent_endpoint = await engine._get_agent_endpoint(agent_slug)
    if agent_endpoint is None:
        return web.json_response(
            {
                _support.SUCCESS_FIELD: False,
                _support.ERROR_FIELD: f"Agent {agent_slug} not found or not running",
            },
            status=_support.HTTP_NOT_FOUND_STATUS,
        )
    delivered = await engine._deliver_to_agent(agent_endpoint, event_data)
    if delivered:
        return web.json_response({_support.SUCCESS_FIELD: True})
    return web.json_response(
        {
            _support.SUCCESS_FIELD: False,
            _support.ERROR_FIELD: "Failed to deliver event to agent",
        },
        status=_support.HTTP_SERVER_ERROR_STATUS,
    )


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
        logger.info("Starting events engine service...")
        self.http_session = ClientSession(
            timeout=ClientTimeout(total=_support.HTTP_SESSION_TIMEOUT_SECONDS)
        )

        self.app = web.Application()
        self.app.router.add_post("/deliver", self._handle_deliver)
        self.app.router.add_get("/healthz", _healthz_handler)

        runner = web.AppRunner(self.app)
        await runner.setup()

        host = os.getenv("EVENTS_ENGINE_HOST", "0.0.0.0")
        port = int(os.getenv("EVENTS_ENGINE_PORT", "8789"))

        site = web.TCPSite(runner, host, port)
        await site.start()
        logger.info("Events engine listening on %s:%s", host, port)

        await asyncio.Event().wait()

    async def stop(self) -> None:
        """Stop the events engine service."""
        logger.info("Stopping events engine service...")
        if self.http_session:
            await self.http_session.close()

    async def _handle_deliver(self, request: web.Request) -> web.Response:
        """Handle event delivery request."""
        try:
            payload = _support.parse_deliver_payload(await request.json())
        except ValueError as exc:
            return web.json_response(
                {_support.SUCCESS_FIELD: False, _support.ERROR_FIELD: str(exc)},
                status=_support.HTTP_BAD_REQUEST_STATUS,
            )
        except Exception as exc:
            logger.error("Error parsing delivery request: %s", exc, exc_info=True)
            return web.json_response(
                {_support.SUCCESS_FIELD: False, _support.ERROR_FIELD: str(exc)},
                status=_support.HTTP_SERVER_ERROR_STATUS,
            )

        return await _process_delivery(self, payload)

    async def _get_agent_endpoint(self, agent_slug: str) -> str | None:
        """Get agent HTTP endpoint from orchestra-agents service."""
        session = self.http_session
        if session is None:
            logger.error("HTTP session is not initialized")
            return None
        url = f"{self.orchestra_agents_url}/api/v1/agents/{agent_slug}/status"
        try:
            async with session.get(url) as response:
                return await _support.extract_agent_endpoint(response, agent_slug)
        except Exception as exc:
            logger.error("Error getting agent endpoint: %s", exc, exc_info=True)
            return None

    async def _deliver_to_agent(self, agent_endpoint: str, event_data: dict[str, Any]) -> bool:
        """Deliver event to agent's /event endpoint."""
        session = self.http_session
        if session is None:
            logger.error("HTTP session is not initialized")
            return False
        url = f"{agent_endpoint}/event"
        logger.info("Delivering event to: %s", url)
        logger.debug("Event data: %s", event_data)
        try:
            async with session.post(url, json=event_data) as response:
                return await _support.handle_agent_delivery_response(response, agent_endpoint)
        except Exception as exc:
            logger.error("Error delivering event to agent: %s", exc, exc_info=True)
            return False
