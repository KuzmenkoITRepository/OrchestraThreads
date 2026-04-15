"""HTTP server for telegram-events: /healthz and /register endpoints."""

from __future__ import annotations

import importlib
from typing import Any
from urllib.parse import urlsplit

from aiohttp import web

_agent_registry = importlib.import_module("core.telegram_events.agent_registry")
RegistrationStatus = _agent_registry.RegistrationStatus

_OK_FIELD = "ok"
_ERROR_FIELD = "error"
_MCP_PATH = "/mcp"
_EXPECTED_SCHEMES = ("http", "https")


async def healthz(request: web.Request) -> web.Response:
    """Return service health status."""
    return web.json_response({_OK_FIELD: True, "service": "telegram-events"})


async def register(request: web.Request) -> web.Response:
    """Register agent ownership for Telegram MCP URL."""
    parsed = await _parse_register_request(request)
    if parsed is None:
        return web.json_response(
            {_OK_FIELD: False, _ERROR_FIELD: "Invalid registration payload"}, status=400
        )
    result = await _run_registration(request, parsed)
    if result.status is RegistrationStatus.CONFLICT:
        return web.json_response(
            {_OK_FIELD: False, _ERROR_FIELD: "telegram_mcp_url already registered"},
            status=409,
        )
    return web.json_response({_OK_FIELD: True})


async def _parse_register_request(request: web.Request) -> tuple[str, str] | None:
    try:
        body = await request.json()
    except Exception:
        return None
    return _parse_register_payload(body)


async def _run_registration(
    request: web.Request,
    parsed: tuple[str, str],
) -> Any:
    agent_slug, telegram_mcp_url = parsed
    agent_registry = request.app["agent_registry"]
    register_agent = request.app["register_agent"]
    return await register_agent(agent_registry, agent_slug, telegram_mcp_url)


def _parse_register_payload(body: Any) -> tuple[str, str] | None:
    if not isinstance(body, dict):
        return None
    agent_slug = body.get("agent_slug")
    telegram_mcp_url = body.get("telegram_mcp_url")
    if not isinstance(agent_slug, str) or not isinstance(telegram_mcp_url, str):
        return None
    normalized_slug = agent_slug.strip()
    normalized_mcp_url = telegram_mcp_url.strip().rstrip("/")
    if not normalized_slug or not normalized_mcp_url:
        return None
    if not _is_valid_telegram_mcp_url(normalized_mcp_url):
        return None
    return normalized_slug, normalized_mcp_url


def _is_valid_telegram_mcp_url(telegram_mcp_url: str) -> bool:
    parsed = urlsplit(telegram_mcp_url)
    if parsed.scheme not in _EXPECTED_SCHEMES:
        return False
    if not parsed.netloc:
        return False
    if parsed.query or parsed.fragment:
        return False
    return parsed.path.rstrip("/") == _MCP_PATH


def build_app() -> web.Application:
    """Create the aiohttp application with routes."""
    app = web.Application()
    app.router.add_get("/healthz", healthz)
    app.router.add_post("/register", register)
    return app
