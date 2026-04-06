"""Events engine service for routing events to agents."""

import asyncio
import logging
import os
from typing import Any, TypedDict

from aiohttp import web
from aiohttp.client import ClientSession, ClientTimeout
from aiohttp.client_reqrep import ClientResponse

logger = logging.getLogger(__name__)


class _DeliverPayload(TypedDict):
    agent_slug: str
    event_data: dict[str, Any]


class _EngineOps:
    @staticmethod
    def parse_deliver_payload(payload: Any) -> _DeliverPayload:
        if not isinstance(payload, dict):
            raise ValueError("Request payload must be an object")
        agent_slug = payload.get("agent_slug")
        if not isinstance(agent_slug, str) or not agent_slug.strip():
            raise ValueError("agent_slug is required")
        event_data = payload.get("event_data")
        if not isinstance(event_data, dict):
            raise ValueError("event_data is required")
        return {
            "agent_slug": agent_slug,
            "event_data": event_data,
        }

    @staticmethod
    def validate_status_data(status_data: dict[str, Any], agent_slug: str) -> str | None:
        if not status_data.get("running"):
            logger.error("Agent %s is not running", agent_slug)
            return None
        health_status = status_data.get("health_status")
        if not isinstance(health_status, dict) or not health_status.get("ok"):
            logger.error("Agent %s is not healthy", agent_slug)
            return None
        endpoint = status_data.get("http_endpoint")
        if isinstance(endpoint, str) and endpoint:
            return endpoint
        logger.error("Agent %s has no http_endpoint", agent_slug)
        return None

    @staticmethod
    async def extract_agent_endpoint(response: ClientResponse, agent_slug: str) -> str | None:
        if response.status != 200:
            logger.error("Failed to get agent status: %s", response.status)
            return None
        raw_data = await response.json()
        if not isinstance(raw_data, dict):
            logger.error("Invalid agent status payload: %s", raw_data)
            return None
        if not raw_data.get("success"):
            logger.error("Agent status request failed: %s", raw_data)
            return None
        status_data = raw_data.get("status")
        if not isinstance(status_data, dict):
            logger.error("Invalid status section for agent %s", agent_slug)
            return None
        return _EngineOps.validate_status_data(status_data, agent_slug)

    @staticmethod
    async def handle_agent_delivery_response(
        response: ClientResponse,
        agent_endpoint: str,
    ) -> bool:
        if response.status == 200:
            logger.info("Successfully delivered event to %s", agent_endpoint)
            return True
        body = await response.text()
        logger.error(
            "Failed to deliver event to %s: status=%s, body=%s",
            agent_endpoint,
            response.status,
            body,
        )
        return False


async def _healthz_handler(request: web.Request) -> web.Response:
    if request:
        return web.json_response({"status": "healthy"})
    return web.json_response({"status": "healthy"})


async def _process_delivery(engine: "EventsEngine", payload: _DeliverPayload) -> web.Response:
    agent_slug = payload["agent_slug"]
    event_data = payload["event_data"]
    logger.info("Delivering event to agent: %s", agent_slug)
    agent_endpoint = await engine._get_agent_endpoint(agent_slug)
    if agent_endpoint is None:
        return web.json_response(
            {
                "success": False,
                "error": f"Agent {agent_slug} not found or not running",
            },
            status=404,
        )
    delivered = await engine._deliver_to_agent(agent_endpoint, event_data)
    if delivered:
        return web.json_response({"success": True})
    return web.json_response(
        {"success": False, "error": "Failed to deliver event to agent"},
        status=500,
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
        self.http_session = ClientSession(timeout=ClientTimeout(total=30.0))

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
            payload = _EngineOps.parse_deliver_payload(await request.json())
        except ValueError as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=400)
        except Exception as exc:
            logger.error("Error parsing delivery request: %s", exc, exc_info=True)
            return web.json_response({"success": False, "error": str(exc)}, status=500)

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
                return await _EngineOps.extract_agent_endpoint(response, agent_slug)
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
                return await _EngineOps.handle_agent_delivery_response(response, agent_endpoint)
        except Exception as exc:
            logger.error("Error delivering event to agent: %s", exc, exc_info=True)
            return False
