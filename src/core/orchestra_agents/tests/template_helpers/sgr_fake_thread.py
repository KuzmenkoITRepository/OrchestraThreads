"""Fake OrchestraThreads HTTP service for SGR backend tests."""

from __future__ import annotations

import socket
from typing import Any

from aiohttp import web

_JsonDict = dict[str, Any]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


class FakeThreadService:  # noqa: WPS214
    """In-process fake of the OrchestraThreads HTTP surface."""

    def __init__(self) -> None:
        self._port = _free_port()
        self.runner: web.AppRunner | None = None
        self.register_calls: list[_JsonDict] = []
        self.heartbeat_calls: list[_JsonDict] = []
        self.message_calls: list[_JsonDict] = []
        self.notification_calls: list[_JsonDict] = []
        self.compact_threads: dict[str, _JsonDict] = {}

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._port}"

    async def start(self) -> None:
        app = web.Application()
        app.router.add_post("/agents/register", self._handle_post)
        app.router.add_post("/agents/heartbeat", self._handle_post)
        app.router.add_post("/api/v1/messages", self._handle_post)
        app.router.add_post("/api/v1/notifications", self._handle_post)
        app.router.add_get("/api/v1/instructions", self._handle_instructions)
        app.router.add_get("/api/v1/threads/{thread_id}/compact", self._handle_threads)
        app.router.add_get("/api/v1/threads/{thread_id}", self._handle_threads)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        await web.TCPSite(self.runner, host="127.0.0.1", port=self._port).start()

    async def stop(self) -> None:
        if self.runner is not None:
            await self.runner.cleanup()
            self.runner = None

    async def _handle_post(self, request: web.Request) -> web.Response:
        payload = await request.json()
        if request.path == "/agents/register":
            return _register_response(self, payload)
        if request.path == "/agents/heartbeat":
            return _heartbeat_response(self, payload)
        if request.path == "/api/v1/messages":
            return _message_response(self, payload)
        self.notification_calls.append(payload)
        return _notification_response(payload)

    async def _handle_instructions(self, request: web.Request) -> web.Response:
        return web.json_response(
            {
                "success": True,
                "instruction": {
                    "text": (
                        "OrchestraThreads guide\n"
                        "Use thread_current first when state is unclear.\n"
                        "Use thread_send for replies and thread_status for lifecycle updates."
                    ),
                    "view": request.query.get("view", "compact"),
                    "section": request.query.get("section", "all"),
                },
            }
        )

    async def _handle_threads(self, request: web.Request) -> web.Response:
        thread_id = request.match_info["thread_id"]
        if request.path.endswith("/compact"):
            return web.json_response(
                {"success": True, "thread": self.compact_threads[thread_id]},
            )
        return web.json_response(
            {
                "success": True,
                "thread": self.compact_threads[thread_id],
                "events": [],
                "related": {},
            }
        )


def _register_response(service: FakeThreadService, payload: _JsonDict) -> web.Response:
    service.register_calls.append(payload)
    return web.json_response(
        {
            "success": True,
            "agent": {
                "agent_slug": payload.get("agent_slug"),
                "base_url": payload.get("base_url"),
            },
            "agent_lease_seconds": 30,
        }
    )


def _heartbeat_response(service: FakeThreadService, payload: _JsonDict) -> web.Response:
    service.heartbeat_calls.append(payload)
    return web.json_response(
        {
            "success": True,
            "agent": {"agent_slug": payload.get("agent_slug")},
        }
    )


def _message_response(service: FakeThreadService, payload: _JsonDict) -> web.Response:
    service.message_calls.append(payload)
    return web.json_response(
        {
            "success": True,
            "operation": "message",
            "created_thread": False,
            "thread": {"thread_id": payload.get("thread_id"), "status": "open"},
            "event": {"event_id": "reply-event-1"},
        }
    )


def _notification_response(payload: _JsonDict) -> web.Response:
    return web.json_response(
        {
            "success": True,
            "operation": "notification",
            "thread": {
                "thread_id": payload.get("thread_id"),
                "status": payload.get("status") or "open",
            },
            "event": {"event_id": "notification-event-1"},
        }
    )
