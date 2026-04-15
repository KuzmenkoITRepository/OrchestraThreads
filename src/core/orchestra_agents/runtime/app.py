"""Reusable aiohttp app for the standard Orchestra agent contract."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

import httpx
from aiohttp import web

from core.orchestra_agents.runtime.backend import BaseAgentBackend
from core.orchestra_agents.runtime.contracts import (
    ClearContextRequest,
    EventDelivery,
    StopRequest,
)

_REGISTRATION_RETRY_ATTEMPTS = 5
_REGISTRATION_RETRY_DELAY_SECONDS = 1.0


def _json_error(message: str, *, status: int) -> web.Response:
    return web.json_response({"success": False, "error": message}, status=status)


def _registration_request(agent_slug: str) -> tuple[str, dict[str, str]] | None:
    telegram_events_url = os.getenv("TELEGRAM_EVENTS_URL", "").strip()
    telegram_mcp_url = os.getenv("BETTER_TELEGRAM_MCP_URL", "").strip()
    if not telegram_events_url or not telegram_mcp_url:
        return None
    return (
        f"{telegram_events_url.rstrip('/')}/register",
        {
            "agent_slug": agent_slug,
            "telegram_mcp_url": telegram_mcp_url.rstrip("/"),
        },
    )


async def _start_site(site: web.TCPSite, app: StandardAgentApplication) -> None:
    await site.start()
    await app._register_self()


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
        try:
            await _start_site(site, self)
        except Exception:
            await self.stop()
            raise

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

    async def _register_self(self) -> None:
        request_data = _registration_request(self.backend.agent_slug)
        if request_data is None:
            return
        registration_url, registration_payload = request_data
        response = await _post_registration_attempt(
            registration_url,
            registration_payload,
            attempts_left=_REGISTRATION_RETRY_ATTEMPTS,
        )
        _validate_registration_response(response)


async def _post_registration_attempt(
    registration_url: str,
    registration_payload: dict[str, str],
    *,
    attempts_left: int,
) -> httpx.Response:
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=30.0) as client:
            return await client.post(registration_url, json=registration_payload)
    except httpx.TransportError as exc:
        if attempts_left <= 1:
            raise RuntimeError("telegram-events self-registration failed") from exc
        await asyncio.sleep(_REGISTRATION_RETRY_DELAY_SECONDS)
        return await _post_registration_attempt(
            registration_url,
            registration_payload,
            attempts_left=attempts_left - 1,
        )


def _validate_registration_response(response: httpx.Response) -> None:
    if response.status_code != 200:
        raise RuntimeError(
            f"telegram-events self-registration failed with status {response.status_code}"
        )
    try:
        response_payload = response.json()
    except ValueError as exc:
        raise RuntimeError("telegram-events self-registration returned malformed response") from exc
    if response_payload != {"ok": True}:
        raise RuntimeError("telegram-events self-registration returned malformed response")
