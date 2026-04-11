from __future__ import annotations

from typing import Any

import httpx

from core.telegram_events.service_logging import logger


async def forward_delivery(
    client: httpx.AsyncClient | None,
    endpoint: str,
    delivery_payload: dict[str, Any],
    message_data: dict[str, Any],
) -> None:
    """POST a delivery payload to events-engine and log the result."""
    bound_client = _require_client(client)
    if bound_client is None:
        return
    try:
        response = await bound_client.post(endpoint, json=delivery_payload)
    except Exception as exc:
        logger.error("Error forwarding message to events-engine: %s", exc, exc_info=True)
        return
    _log_delivery_response(response, message_data)


def _require_client(client: httpx.AsyncClient | None) -> httpx.AsyncClient | None:
    if client is not None:
        return client
    logger.error("HTTP client not initialized")
    return None


def _log_delivery_response(
    response: httpx.Response,
    message_data: dict[str, Any],
) -> None:
    if response.status_code == 200:
        logger.info(
            "Successfully forwarded message %s to events-engine",
            message_data.get("message_id"),
        )
        return
    logger.error(
        "Failed to forward message to events-engine: status=%s, body=%s",
        response.status_code,
        response.text,
    )
