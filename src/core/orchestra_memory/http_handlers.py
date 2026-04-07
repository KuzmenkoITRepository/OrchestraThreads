from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from aiohttp import web


class _MemoryServiceProtocol(Protocol):
    async def is_healthy(self) -> bool: ...

    async def remember(
        self,
        *,
        agent_slug: str,
        room: str,
        category: str,
        text: str,
    ) -> dict[str, str]: ...

    async def search(
        self,
        *,
        agent_slug: str,
        query: str,
        room: str | None,
        category: str | None,
        limit: int,
    ) -> list[dict[str, str]]: ...

    async def delete(self, *, agent_slug: str, memory_id: str) -> bool: ...

    async def clear(self, *, agent_slug: str, room: str | None, category: str | None) -> int: ...


def json_error(message: str, *, status: int) -> web.Response:
    return web.json_response({"success": False, "error": message}, status=status)


def json_success(payload: dict[str, Any]) -> web.Response:
    return web.json_response(payload)


class _PayloadReader:
    @staticmethod
    def required(payload: dict[str, Any], field_name: str) -> str:
        value = payload.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must be a non-empty string")
        return value.strip()

    @staticmethod
    def optional_str(payload: dict[str, Any], field_name: str) -> str:
        value = payload.get(field_name)
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ValueError(f"{field_name} must be a string")
        return value

    @staticmethod
    def optional_nullable(payload: dict[str, Any], field_name: str) -> str | None:
        value = payload.get(field_name)
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError(f"{field_name} must be a string or null")
        return value

    @staticmethod
    def optional_int(payload: dict[str, Any], field_name: str, default: int) -> int:
        value = payload.get(field_name)
        if value is None:
            return default
        if not isinstance(value, int):
            raise ValueError(f"{field_name} must be an integer")
        return value


@dataclass(frozen=True)
class MemoryHttpHandlers:
    service: _MemoryServiceProtocol

    async def healthz(self, _: web.Request) -> web.Response:
        if not await self.service.is_healthy():
            return web.json_response({"status": "error"}, status=503)
        return json_success({"status": "ok"})

    async def remember(self, request: web.Request) -> web.Response:
        payload = await request.json()
        try:
            saved = await self.service.remember(
                agent_slug=_PayloadReader.required(payload, "agent_slug"),
                room=_PayloadReader.required(payload, "room"),
                category=_PayloadReader.required(payload, "category"),
                text=_PayloadReader.required(payload, "text"),
            )
        except ValueError as exc:
            return json_error(str(exc), status=400)
        return json_success({"memory": saved})

    async def search(self, request: web.Request) -> web.Response:
        payload = await request.json()
        try:
            result = await self.service.search(
                agent_slug=_PayloadReader.required(payload, "agent_slug"),
                query=_PayloadReader.optional_str(payload, "query"),
                room=_PayloadReader.optional_nullable(payload, "room"),
                category=_PayloadReader.optional_nullable(payload, "category"),
                limit=_PayloadReader.optional_int(payload, "limit", 20),
            )
        except ValueError as exc:
            return json_error(str(exc), status=400)
        return json_success({"items": result})

    async def delete(self, request: web.Request) -> web.Response:
        payload = await request.json()
        try:
            deleted = await self.service.delete(
                agent_slug=_PayloadReader.required(payload, "agent_slug"),
                memory_id=_PayloadReader.required(payload, "memory_id"),
            )
        except ValueError as exc:
            return json_error(str(exc), status=400)
        if not deleted:
            return json_error("memory not found", status=404)
        return json_success({"deleted": True})

    async def clear(self, request: web.Request) -> web.Response:
        payload = await request.json()
        try:
            deleted_count = await self.service.clear(
                agent_slug=_PayloadReader.required(payload, "agent_slug"),
                room=_PayloadReader.optional_nullable(payload, "room"),
                category=_PayloadReader.optional_nullable(payload, "category"),
            )
        except ValueError as exc:
            return json_error(str(exc), status=400)
        return json_success({"deleted_count": deleted_count})
