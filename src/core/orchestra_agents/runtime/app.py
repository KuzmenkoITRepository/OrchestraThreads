"""Reusable aiohttp app for the standard Orchestra agent contract."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from aiohttp import web

from core.orchestra_agents.runtime.backend import BaseAgentBackend
from core.orchestra_agents.runtime.contracts import (
    ClearContextRequest,
    EventDelivery,
    StopRequest,
)


def _json_error(message: str, *, status: int) -> web.Response:
    return web.json_response({"success": False, "error": message}, status=status)


@dataclass(frozen=True)
class _RequestHandlers:
    backend: BaseAgentBackend

    async def healthz(self, _: web.Request) -> web.Response:
        return web.json_response(await self.backend.health())

    async def event(self, request: web.Request) -> web.Response:
        payload = await request.json()
        try:
            delivery = EventDelivery.from_dict(payload)
        except Exception as exc:
            return _json_error(str(exc), status=400)
        return web.json_response((await self.backend.handle_events(delivery)).to_dict())

    async def stop(self, request: web.Request) -> web.Response:
        payload = await request.json()
        return web.json_response(await self.backend.stop(StopRequest.from_dict(payload)))

    async def last_status(self, _: web.Request) -> web.Response:
        return web.json_response(await self.backend.last_status())

    async def clear_context(self, request: web.Request) -> web.Response:
        payload = await request.json()
        cleared = await self.backend.clear_context(ClearContextRequest.from_dict(payload))
        return web.json_response(cleared)


class StandardAgentApplication:
    """Small HTTP runtime wrapper around a backend adapter."""

    def __init__(
        self,
        *,
        backend: BaseAgentBackend,
        host: str = "0.0.0.0",
        port: int = 8787,
    ) -> None:
        self.backend = backend
        self.host = host
        self.port = int(port)
        self.runner: web.AppRunner | None = None

    def build_app(self) -> web.Application:
        app = web.Application()
        handlers = _RequestHandlers(self.backend)
        app.router.add_get("/healthz", handlers.healthz)
        app.router.add_post("/event", handlers.event)
        app.router.add_post("/stop", handlers.stop)
        app.router.add_get("/last_status", handlers.last_status)
        app.router.add_post("/clear_context", handlers.clear_context)
        return app

    async def start(self) -> None:
        if self.runner is not None:
            return
        await self.backend.on_start()
        self.runner = web.AppRunner(self.build_app())
        await self.runner.setup()
        site = web.TCPSite(self.runner, host=self.host, port=self.port)
        await site.start()

    async def stop(self) -> None:
        runner = self.runner
        if runner is None:
            return
        self.runner = None
        await runner.cleanup()
        await self.backend.on_shutdown()

    async def serve_forever(self) -> None:
        await self.start()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            raise
        finally:
            await self.stop()
