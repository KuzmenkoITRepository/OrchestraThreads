from __future__ import annotations

import httpx

from core.telegram_events import clear_command as _clear
from core.telegram_events.service_logging import logger


async def resolve_clear_endpoint(
    *,
    client: httpx.AsyncClient | None,
    orchestra_agents_url: str,
    agent_slug: str,
) -> str | None:
    """Resolve the target runtime clear_context endpoint from orchestra-agents."""
    response = await _status_response(client, orchestra_agents_url, agent_slug)
    if response is None:
        logger.error("Failed to resolve clear_context endpoint for %s", agent_slug)
        return None
    return _clear.clear_endpoint_from_status(response.json(), agent_slug)


async def clear_agent_context(
    client: httpx.AsyncClient | None,
    endpoint: str,
    routing_key: str,
) -> bool:
    """Call the agent runtime clear_context endpoint for a chat routing key."""
    bound_client = _require_client(client)
    if bound_client is None:
        return False
    payload = {
        "requested_by": "telegram_events:/clear",
        "routing_key": routing_key,
    }
    try:
        response = await bound_client.post(endpoint, json=payload)
    except Exception as exc:
        logger.error("Failed to clear context via %s: %s", endpoint, exc, exc_info=True)
        return False
    if response.status_code == 200:
        logger.info("Cleared context for routing_key=%s", routing_key)
        return True
    logger.error(
        "Failed to clear context via %s: status=%s body=%s",
        endpoint,
        response.status_code,
        response.text,
    )
    return False


def _require_client(client: httpx.AsyncClient | None) -> httpx.AsyncClient | None:
    if client is not None:
        return client
    logger.error("HTTP client not initialized")
    return None


async def _status_response(
    client: httpx.AsyncClient | None,
    orchestra_agents_url: str,
    agent_slug: str,
) -> httpx.Response | None:
    bound_client = _require_client(client)
    if bound_client is None:
        return None
    status_url = f"{orchestra_agents_url}/api/v1/agents/{agent_slug}/status"
    try:
        response = await bound_client.get(status_url)
    except Exception as exc:
        logger.error("Failed to fetch agent status for %s: %s", agent_slug, exc, exc_info=True)
        return None
    if response.status_code == 200:
        return response
    logger.error(
        "Agent status request failed for %s: status=%s body=%s",
        agent_slug,
        response.status_code,
        response.text,
    )
    return None
