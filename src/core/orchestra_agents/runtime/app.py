"""Reusable aiohttp app for the standard Orchestra agent contract."""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from aiohttp import web

from .backend import BaseAgentBackend
from .contracts import ClearContextRequest, EventDelivery, StopRequest


def _json_error(message: str, *, status: int) -> web.Response:
    return web.json_response({"success": False, "error": message}, status=status)


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
        self.runner: Optional[web.AppRunner] = None

    def build_app(self) -> web.Application:
        app = web.Application()
        app.router.add_get("/healthz", self._handle_healthz)
        app.router.add_post("/event", self._handle_event)
        app.router.add_post("/stop", self._handle_stop)
        app.router.add_get("/last_status", self._handle_last_status)
        app.router.add_post("/clear_context", self._handle_clear_context)
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
        if self.runner is None:
            return
        await self.runner.cleanup()
        self.runner = None
        await self.backend.on_shutdown()

    async def serve_forever(self) -> None:
        await self.start()
        try:
            await asyncio.Event().wait()
        finally:
            await self.stop()

    async def _handle_healthz(self, request: web.Request) -> web.Response:
        del request
        return web.json_response(await self.backend.health())

    async def _handle_event(self, request: web.Request) -> web.Response:
        payload = await request.json()
        try:
            delivery = EventDelivery.from_dict(payload)
        except Exception as exc:
            return _json_error(str(exc), status=400)
        result = await self.backend.handle_events(delivery)
        return web.json_response(result.to_dict())

    async def _handle_stop(self, request: web.Request) -> web.Response:
        payload = await request.json()
        result = await self.backend.stop(StopRequest.from_dict(payload))
        return web.json_response(result)

    async def _handle_last_status(self, request: web.Request) -> web.Response:
        del request
        return web.json_response(await self.backend.last_status())

    async def _handle_clear_context(self, request: web.Request) -> web.Response:
        payload = await request.json()
        result = await self.backend.clear_context(ClearContextRequest.from_dict(payload))
        return web.json_response(result)
