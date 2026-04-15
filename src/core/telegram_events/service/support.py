from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any

from aiohttp import web

from core.telegram_events.http_server import build_app
from core.telegram_events.service_logging import logger

_PROXY_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "http_proxy",
    "https_proxy",
    "ALL_PROXY",
    "all_proxy",
    "NO_PROXY",
    "no_proxy",
)


@dataclass(frozen=True)
class ForwardingConfig:
    events_engine_url: str = "http://events-engine:8789"


def log_startup(
    events_engine_url: str,
    http_host: str,
    http_port: int,
) -> None:
    logger.info("Starting Telegram events service...")
    logger.info("Events engine endpoint: %s", events_engine_url)
    logger.info("HTTP server bind: %s:%s", http_host, http_port)


def resolve_forwarding_config(options: dict[str, Any]) -> ForwardingConfig:
    return ForwardingConfig(
        events_engine_url=str(options.get("events_engine_url", "http://events-engine:8789")),
    )


async def start_http_server(
    http_host: str,
    http_port: int,
    agent_registry: Any | None = None,
    register_agent: Any | None = None,
) -> web.AppRunner:
    app = build_app()
    if agent_registry is not None:
        app["agent_registry"] = agent_registry
    if register_agent is not None:
        app["register_agent"] = register_agent
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=http_host, port=http_port)
    await site.start()
    return runner


def clear_proxy_env() -> None:
    for key in _PROXY_KEYS:
        os.environ.pop(key, None)


async def wait_for_shutdown(
    shutdown_future: asyncio.Future[None],
) -> None:
    await shutdown_future
