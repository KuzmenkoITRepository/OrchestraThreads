from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from aiohttp import web

from core.orchestra_thread.common import ServiceError
from core.orchestra_thread.service_shared import (
    STATIC_DIR,
    json_error,
    json_success,
    service_error_response,
)

_RequestHandler = Callable[[web.Request], Awaitable[web.StreamResponse]]


class _ServiceHandlerBase:
    def __init__(self, service: Any) -> None:
        self._service = service

    async def _json_from_service(self, operation: Awaitable[Any]) -> web.Response:
        try:
            return json_success(await operation)
        except ServiceError as exc:
            return service_error_response(exc)


class HttpReadHandlers(_ServiceHandlerBase):
    async def handle_ui(self, _: web.Request) -> web.StreamResponse:
        index_path = STATIC_DIR / "index.html"
        if not index_path.exists():
            return json_error("OrchestraThreads UI is not available", status=404)
        return web.FileResponse(index_path)

    async def handle_health(self, _: web.Request) -> web.Response:
        payload, status_code = await self._service.health_snapshot()
        return web.json_response(payload, status=status_code)

    async def handle_agents(self, _: web.Request) -> web.Response:
        return await self._json_from_service(self._service.list_agents())

    async def handle_agent_status(self, request: web.Request) -> web.Response:
        agent_slug = str(request.match_info.get("agent_slug") or "").strip()
        return await self._json_from_service(self._service.get_agent_status(agent_slug))

    async def handle_threads(self, request: web.Request) -> web.Response:
        return await self._json_from_service(
            self._service.list_threads(
                scope=str(request.query.get("scope", "active")),
                limit=max(1, int(request.query.get("limit", "100"))),
            )
        )

    async def handle_thread(self, request: web.Request) -> web.Response:
        return await self._json_from_service(
            self._service.get_thread(
                thread_id=str(request.match_info.get("thread_id") or ""),
                limit=max(1, int(request.query.get("limit", "200"))),
            )
        )

    async def handle_thread_compact(self, request: web.Request) -> web.Response:
        return await self._json_from_service(
            self._service.get_thread_compact(
                thread_id=str(request.match_info.get("thread_id") or ""),
            )
        )


class HttpInstructionHandlers(_ServiceHandlerBase):
    async def handle_instructions(self, request: web.Request) -> web.Response:
        return await self._json_from_service(
            self._service.get_instruction(
                view=str(request.query.get("view", "compact")),
                section=str(request.query.get("section") or "").strip() or None,
            )
        )


class HttpWriteHandlers(_ServiceHandlerBase):
    async def handle_register(self, request: web.Request) -> web.Response:
        return await self._json_from_service(
            self._service.register_agent(await request.json()),
        )

    async def handle_heartbeat(self, request: web.Request) -> web.Response:
        return await self._json_from_service(
            self._service.heartbeat(await request.json()),
        )

    async def handle_messages(self, request: web.Request) -> web.Response:
        payload = await request.json()
        try:
            return await self._json_from_service(
                self._service.send_message(legacy_kwargs=_message_payload(payload))
            )
        except Exception as exc:
            return json_error(str(exc) or "internal server error", status=500)

    async def handle_notifications(self, request: web.Request) -> web.Response:
        payload = await request.json()
        try:
            return await self._json_from_service(
                self._service.send_notification(legacy_kwargs=_notification_payload(payload))
            )
        except Exception as exc:
            return json_error(str(exc) or "internal server error", status=500)


def _message_payload(payload: dict[str, object]) -> dict[str, object]:
    return {
        "from_agent_slug": str(payload.get("from_agent_slug") or "").strip(),
        "to_agent_slug": str(payload.get("to_agent_slug") or "").strip(),
        "message_text": str(payload.get("message_text") or ""),
        "thread_id": str(payload.get("thread_id") or "").strip() or None,
        "parent_thread_id": str(payload.get("parent_thread_id") or "").strip() or None,
        "client_request_id": str(payload.get("client_request_id") or "").strip()
        or uuid.uuid4().hex,
    }


def _notification_payload(payload: dict[str, object]) -> dict[str, object]:
    return {
        "from_agent_slug": str(payload.get("from_agent_slug") or "").strip(),
        "to_agent_slug": str(payload.get("to_agent_slug") or "").strip(),
        "thread_id": str(payload.get("thread_id") or "").strip(),
        "status": str(payload.get("status") or "").strip(),
        "message_text": str(payload.get("message_text") or ""),
        "client_request_id": str(payload.get("client_request_id") or "").strip()
        or uuid.uuid4().hex,
    }


class HttpHandlers:
    def __init__(self, service: Any) -> None:
        read_handlers = HttpReadHandlers(service)
        instruction_handlers = HttpInstructionHandlers(service)
        write_handlers = HttpWriteHandlers(service)

        self._handlers: dict[str, _RequestHandler] = {
            "handle_ui": read_handlers.handle_ui,
            "handle_health": read_handlers.handle_health,
            "handle_register": write_handlers.handle_register,
            "handle_heartbeat": write_handlers.handle_heartbeat,
            "handle_agents": read_handlers.handle_agents,
            "handle_agent_status": read_handlers.handle_agent_status,
            "handle_messages": write_handlers.handle_messages,
            "handle_notifications": write_handlers.handle_notifications,
            "handle_threads": read_handlers.handle_threads,
            "handle_thread": read_handlers.handle_thread,
            "handle_thread_compact": read_handlers.handle_thread_compact,
            "handle_instructions": instruction_handlers.handle_instructions,
        }

    def __getattr__(self, name: str) -> _RequestHandler:
        handler = self._handlers.get(name)
        if handler is None:
            raise AttributeError(name)
        return handler
