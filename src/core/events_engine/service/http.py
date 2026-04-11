"""HTTP handlers for events_engine."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiohttp import web

from core.events_engine.service import support

if TYPE_CHECKING:
    from core.events_engine.service.runtime import EventsEngine


async def healthz_handler(_request: web.Request) -> web.Response:
    return web.json_response({"status": "healthy"})


async def process_delivery(
    engine: EventsEngine,
    payload: support.DeliverPayload,
) -> web.Response:
    agent_slug = payload["agent_slug"]
    event_data = payload["event_data"]
    support.logger.info("Delivering event to agent: %s", agent_slug)
    agent_endpoint = await engine._get_agent_endpoint(agent_slug)
    if agent_endpoint is None:
        return web.json_response(
            {
                support.SUCCESS_FIELD: False,
                support.ERROR_FIELD: f"Agent {agent_slug} not found or not running",
            },
            status=support.HTTP_NOT_FOUND_STATUS,
        )
    delivered = await engine._deliver_to_agent(agent_endpoint, event_data)
    if delivered:
        return web.json_response({support.SUCCESS_FIELD: True})
    return web.json_response(
        {
            support.SUCCESS_FIELD: False,
            support.ERROR_FIELD: "Failed to deliver event to agent",
        },
        status=support.HTTP_SERVER_ERROR_STATUS,
    )


async def handle_deliver(engine: EventsEngine, request: web.Request) -> web.Response:
    """Handle event delivery request."""
    try:
        payload = support.parse_deliver_payload(await request.json())
    except ValueError as exc:
        return web.json_response(
            {support.SUCCESS_FIELD: False, support.ERROR_FIELD: str(exc)},
            status=support.HTTP_BAD_REQUEST_STATUS,
        )
    except Exception as exc:
        support.logger.error("Error parsing delivery request: %s", exc, exc_info=True)
        return web.json_response(
            {support.SUCCESS_FIELD: False, support.ERROR_FIELD: str(exc)},
            status=support.HTTP_SERVER_ERROR_STATUS,
        )

    return await process_delivery(engine, payload)
