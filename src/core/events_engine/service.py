"""Events engine service for routing events to agents."""

import asyncio
import logging
import os

import aiohttp
from aiohttp import web

logger = logging.getLogger(__name__)


class EventsEngine:
    """Routes events from external sources to agents via their /event endpoints."""

    def __init__(
        self,
        orchestra_agents_url: str = "http://orchestra-agents:8790",
    ):
        self.orchestra_agents_url = orchestra_agents_url
        self.http_session: aiohttp.ClientSession | None = None
        self.app: web.Application | None = None

    async def start(self):
        """Start the events engine service."""
        logger.info("Starting events engine service...")

        self.http_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30.0))

        self.app = web.Application()
        self.app.router.add_post("/deliver", self._handle_deliver)
        self.app.router.add_get("/healthz", self._handle_healthz)

        runner = web.AppRunner(self.app)
        await runner.setup()

        host = os.getenv("EVENTS_ENGINE_HOST", "0.0.0.0")
        port = int(os.getenv("EVENTS_ENGINE_PORT", "8789"))

        site = web.TCPSite(runner, host, port)
        await site.start()

        logger.info(f"Events engine listening on {host}:{port}")

        await asyncio.Event().wait()

    async def stop(self):
        """Stop the events engine service."""
        logger.info("Stopping events engine service...")

        if self.http_session:
            await self.http_session.close()

    async def _handle_healthz(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response({"status": "healthy"})

    async def _handle_deliver(self, request: web.Request) -> web.Response:
        """Handle event delivery request."""
        try:
            payload = await request.json()

            agent_slug = payload.get("agent_slug")
            event_data = payload.get("event_data")

            if not agent_slug:
                return web.json_response(
                    {"success": False, "error": "agent_slug is required"}, status=400
                )

            if not event_data:
                return web.json_response(
                    {"success": False, "error": "event_data is required"}, status=400
                )

            logger.info(f"Delivering event to agent: {agent_slug}")

            agent_endpoint = await self._get_agent_endpoint(agent_slug)
            if not agent_endpoint:
                return web.json_response(
                    {
                        "success": False,
                        "error": f"Agent {agent_slug} not found or not running",
                    },
                    status=404,
                )

            success = await self._deliver_to_agent(agent_endpoint, event_data)

            if success:
                return web.json_response({"success": True})
            else:
                return web.json_response(
                    {"success": False, "error": "Failed to deliver event to agent"},
                    status=500,
                )

        except Exception as e:
            logger.error(f"Error handling delivery request: {e}", exc_info=True)
            return web.json_response({"success": False, "error": str(e)}, status=500)

    async def _get_agent_endpoint(self, agent_slug: str) -> str | None:
        """Get agent HTTP endpoint from orchestra-agents service."""
        try:
            url = f"{self.orchestra_agents_url}/api/v1/agents/{agent_slug}/status"

            async with self.http_session.get(url) as response:
                if response.status != 200:
                    logger.error(f"Failed to get agent status: {response.status}")
                    return None

                data = await response.json()

                if not data.get("success"):
                    logger.error(f"Agent status request failed: {data}")
                    return None

                status = data.get("status", {})

                if not status.get("running"):
                    logger.error(f"Agent {agent_slug} is not running")
                    return None

                health_status = status.get("health_status", {})
                if not health_status.get("ok"):
                    logger.error(f"Agent {agent_slug} is not healthy")
                    return None

                endpoint = status.get("http_endpoint")
                if not endpoint:
                    logger.error(f"Agent {agent_slug} has no http_endpoint")
                    return None

                return endpoint

        except Exception as e:
            logger.error(f"Error getting agent endpoint: {e}", exc_info=True)
            return None

    async def _deliver_to_agent(self, agent_endpoint: str, event_data: dict) -> bool:
        """Deliver event to agent's /event endpoint."""
        try:
            url = f"{agent_endpoint}/event"

            logger.info(f"Delivering event to: {url}")
            logger.debug(f"Event data: {event_data}")

            async with self.http_session.post(url, json=event_data) as response:
                if response.status == 200:
                    logger.info(f"Successfully delivered event to {agent_endpoint}")
                    return True
                else:
                    body = await response.text()
                    logger.error(
                        f"Failed to deliver event to {agent_endpoint}: "
                        f"status={response.status}, body={body}"
                    )
                    return False

        except Exception as e:
            logger.error(f"Error delivering event to agent: {e}", exc_info=True)
            return False
