from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from typing import TYPE_CHECKING

from aiohttp import web

from core.telegram_events.relay_compat_http import build_relay_compat_app
from core.telegram_events.relay_compat_payloads import build_sse_event_payload

if TYPE_CHECKING:
    from core.telegram_events.relay_compat_http import RelayCompatServiceProtocol


async def start_http_server(
    service: RelayCompatServiceProtocol,
    bearer_token: str,
    host: str,
    port: int,
) -> web.AppRunner:
    app = build_relay_compat_app(service, bearer_token)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
    return runner


def enqueue_payload(subscriber: asyncio.Queue[str | None], payload: str) -> None:
    with suppress(asyncio.QueueEmpty):
        if subscriber.full():
            subscriber.get_nowait()
    subscriber.put_nowait(payload)


async def broadcast_payload(
    subscribers: set[asyncio.Queue[str | None]],
    payload: str,
) -> None:
    for subscriber in list(subscribers):
        enqueue_payload(subscriber, payload)


async def close_subscribers(subscribers: set[asyncio.Queue[str | None]]) -> None:
    for subscriber in list(subscribers):
        with suppress(asyncio.QueueFull):
            subscriber.put_nowait(None)


def serialize_message_payload(message_data: dict[str, object]) -> str:
    return json.dumps(build_sse_event_payload(message_data))
