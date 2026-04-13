"""HTTP helper utilities for remote MCP clients."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


def build_payload(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Build JSON-RPC payload for a tools/call request."""
    return {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": name,
            "arguments": arguments,
        },
        "id": 1,
    }


def build_headers(bearer_token: str) -> dict[str, str]:
    """Build HTTP headers with Bearer auth."""
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {bearer_token}",
    }


async def execute_call(
    session: aiohttp.ClientSession,
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
) -> dict[str, Any]:
    """Execute HTTP call and parse response."""
    async with session.post(url, json=payload, headers=headers) as response:
        status_error = check_status(response.status, payload)
        if status_error is not None:
            return status_error

        response.raise_for_status()
        result = await response.json()
        return parse_result(result)


def check_status(
    status_code: int,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    """Return error dict for non-2xx HTTP status."""
    tool_name = payload["params"]["name"]
    if status_code == 401:
        logger.error("Remote MCP auth failed for %s", tool_name)
        return {"ok": False, "error": "Authentication failed", "status_code": 401}
    if status_code == 403:
        logger.error("Remote MCP forbidden for %s", tool_name)
        return {"ok": False, "error": "Access forbidden", "status_code": 403}
    if status_code >= 500:
        logger.error("Remote MCP server error for %s: %d", tool_name, status_code)
        return {"ok": False, "error": f"Server error: {status_code}", "status_code": status_code}
    return None


def parse_result(result: dict[str, Any]) -> dict[str, Any]:
    """Extract result or error from JSON-RPC payload."""
    error_data = result.get("error")
    if error_data is not None and isinstance(error_data, dict):
        return _build_error_response(error_data)
    raw_result = result.get("result")
    if isinstance(raw_result, dict):
        return raw_result
    return {"ok": True}


def _build_error_response(error_data: dict[str, Any]) -> dict[str, Any]:
    """Build error response dict."""
    return {
        "ok": False,
        "error": error_data.get("message", "Unknown error"),
        "code": error_data.get("code"),
    }
