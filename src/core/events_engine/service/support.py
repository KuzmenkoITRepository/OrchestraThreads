from __future__ import annotations

import logging
from typing import Any, TypedDict

from aiohttp.client_reqrep import ClientResponse

logger = logging.getLogger(__name__)

HTTP_OK_STATUS = 200
HTTP_BAD_REQUEST_STATUS = 400
HTTP_NOT_FOUND_STATUS = 404
HTTP_SERVER_ERROR_STATUS = 500
HTTP_SESSION_TIMEOUT_SECONDS = 30.0
SUCCESS_FIELD = "success"
ERROR_FIELD = "error"


class DeliverPayload(TypedDict):
    agent_slug: str
    event_data: dict[str, Any]


def parse_deliver_payload(payload: Any) -> DeliverPayload:
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


async def extract_agent_endpoint(response: ClientResponse, agent_slug: str) -> str | None:
    if response.status != HTTP_OK_STATUS:
        logger.error("Failed to get agent status: %s", response.status)
        return None
    raw_data = await response.json()
    if not isinstance(raw_data, dict):
        logger.error("Invalid agent status payload: %s", raw_data)
        return None
    if not raw_data.get(SUCCESS_FIELD):
        logger.error("Agent status request failed: %s", raw_data)
        return None
    status_data = raw_data.get("status")
    if not isinstance(status_data, dict):
        logger.error("Invalid status section for agent %s", agent_slug)
        return None
    return validate_status_data(status_data, agent_slug)


async def handle_agent_delivery_response(
    response: ClientResponse,
    agent_endpoint: str,
) -> bool:
    if response.status == HTTP_OK_STATUS:
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
