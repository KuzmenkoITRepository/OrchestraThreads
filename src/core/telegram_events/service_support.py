from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any, cast

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
    target_agent_slug: str = "secretary"


def log_startup(
    events_engine_url: str,
    target_agent_slug: str,
    http_host: str,
    http_port: int,
) -> None:
    logger.info("Starting Telegram events service...")
    logger.info("Events engine endpoint: %s", events_engine_url)
    logger.info("Target agent: %s", target_agent_slug)
    logger.info("HTTP server bind: %s:%s", http_host, http_port)


def resolve_forwarding_config(options: dict[str, Any]) -> ForwardingConfig:
    return ForwardingConfig(
        events_engine_url=str(options.get("events_engine_url", "http://events-engine:8789")),
        target_agent_slug=str(options.get("target_agent_slug", "secretary")),
    )


async def start_http_server(
    client: Any,
    http_host: str,
    http_port: int,
) -> web.AppRunner:
    app = build_app()
    app["telethon_client"] = client
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=http_host, port=http_port)
    await site.start()
    return runner


def clear_proxy_env() -> None:
    import os

    for key in _PROXY_KEYS:
        os.environ.pop(key, None)


async def wait_for_shutdown(
    listener_waiter: Awaitable[None],
    shutdown_future: asyncio.Future[None],
) -> None:
    await asyncio.gather(listener_waiter, shutdown_future)


def listener_task(client: Any) -> Awaitable[None]:
    return cast(Awaitable[None], client.run_until_disconnected())
