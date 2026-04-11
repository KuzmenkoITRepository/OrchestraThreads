"""Agent delivery operations for events_engine."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.events_engine.service import support

if TYPE_CHECKING:
    from aiohttp.client import ClientSession


def _resolve_session(session: ClientSession | None) -> ClientSession | None:
    if session is None:
        support.logger.error("HTTP session is not initialized")
        return None
    return session


async def get_agent_endpoint(
    http_session: ClientSession | None,
    orchestra_agents_url: str,
    agent_slug: str,
) -> str | None:
    """Get agent HTTP endpoint from orchestra-agents service."""
    session = _resolve_session(http_session)
    if session is None:
        return None
    url = f"{orchestra_agents_url}/api/v1/agents/{agent_slug}/status"
    try:
        async with session.get(url) as response:
            return await support.extract_agent_endpoint(response, agent_slug)
    except Exception as exc:
        support.logger.error("Error getting agent endpoint: %s", exc, exc_info=True)
        return None


async def deliver_to_agent(
    http_session: ClientSession | None,
    agent_endpoint: str,
    event_data: dict[str, Any],
) -> bool:
    """Deliver event to agent's /event endpoint."""
    session = _resolve_session(http_session)
    if session is None:
        return False
    url = f"{agent_endpoint}/event"
    support.logger.info("Delivering event to: %s", url)
    support.logger.debug("Event data: %s", event_data)
    try:
        async with session.post(url, json=event_data) as response:
            return await support.handle_agent_delivery_response(response, agent_endpoint)
    except Exception as exc:
        support.logger.error("Error delivering event to agent: %s", exc, exc_info=True)
        return False
