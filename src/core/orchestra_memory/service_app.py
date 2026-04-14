from __future__ import annotations

from typing import Protocol

from aiohttp import web

from core.orchestra_memory.http_handlers import MemoryHttpHandlers


class _ServiceProtocol(Protocol):
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

    async def list_rooms(self, *, agent_slug: str) -> list[str]: ...

    async def list_categories(self, *, agent_slug: str) -> list[str]: ...


def build_memory_app(service: _ServiceProtocol) -> web.Application:
    handlers = MemoryHttpHandlers(service)
    app = web.Application()
    app["service"] = service
    app.router.add_get("/healthz", handlers.healthz)
    app.router.add_post("/memory/remember", handlers.remember)
    app.router.add_post("/memory/search", handlers.search)
    app.router.add_post("/memory/delete", handlers.delete)
    app.router.add_post("/memory/clear", handlers.clear)
    app.router.add_post("/memory/discovery/rooms", handlers.discovery_rooms)
    app.router.add_post("/memory/discovery/categories", handlers.discovery_categories)
    return app
