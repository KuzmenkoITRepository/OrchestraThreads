from __future__ import annotations

import asyncio

from aiohttp import web


async def write_sse_events(
    response: web.StreamResponse,
    subscriber: asyncio.Queue[str | None],
) -> None:
    while True:
        payload = await subscriber.get()
        if payload is None:
            return
        await _write_sse_payload(response, payload)


async def _write_sse_payload(response: web.StreamResponse, payload: str) -> None:
    await response.write(f"data: {payload}\n\n".encode())
