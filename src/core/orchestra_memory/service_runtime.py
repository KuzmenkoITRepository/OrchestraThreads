from __future__ import annotations

import asyncio
import logging

from aiohttp import web

from core.orchestra_memory.config import OrchestraMemoryConfig, load_config
from core.orchestra_memory.http_handlers import MemoryHttpHandlers
from core.orchestra_memory.store import OrchestraMemoryStore

logger = logging.getLogger(__name__)


class _ServiceOperations:
    store: OrchestraMemoryStore

    async def remember(
        self,
        *,
        agent_slug: str,
        room: str,
        category: str,
        text: str,
    ) -> dict[str, str]:
        return await self.store.remember(
            agent_slug=agent_slug,
            room=room,
            category=category,
            text=text,
        )

    async def search(
        self,
        *,
        agent_slug: str,
        query: str,
        room: str | None,
        category: str | None,
        limit: int,
    ) -> list[dict[str, str]]:
        return await self.store.search(
            agent_slug=agent_slug,
            query=query,
            room=room,
            category=category,
            limit=limit,
        )

    async def delete(self, *, agent_slug: str, memory_id: str) -> bool:
        return await self.store.delete(agent_slug=agent_slug, memory_id=memory_id)

    async def clear(self, *, agent_slug: str, room: str | None, category: str | None) -> int:
        return await self.store.clear(agent_slug=agent_slug, room=room, category=category)


class OrchestraMemoryService(_ServiceOperations):
    def __init__(self, config: OrchestraMemoryConfig | None = None) -> None:
        self.config = config or load_config()
        self.store = OrchestraMemoryStore(
            storage_path=self.config.storage_path,
            allowed_rooms=self.config.allowed_rooms,
            allowed_categories=self.config.allowed_categories,
        )
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        await self.store.start()
        self._started = True

    async def stop(self) -> None:
        if not self._started:
            return
        await self.store.close()
        self._started = False

    async def is_healthy(self) -> bool:
        return await self.store.ping()


def build_app(service: OrchestraMemoryService) -> web.Application:
    handlers = MemoryHttpHandlers(service)
    app = web.Application()
    app["service"] = service
    app.router.add_get("/healthz", handlers.healthz)
    app.router.add_post("/memory/remember", handlers.remember)
    app.router.add_post("/memory/search", handlers.search)
    app.router.add_post("/memory/delete", handlers.delete)
    app.router.add_post("/memory/clear", handlers.clear)
    return app


async def _start_site(service: OrchestraMemoryService) -> web.AppRunner:
    runner = web.AppRunner(build_app(service))
    await runner.setup()
    site = web.TCPSite(runner, host=service.config.host, port=service.config.port)
    await site.start()
    return runner


async def run_service() -> None:
    service = OrchestraMemoryService()
    await service.start()
    runner = await _start_site(service)
    logger.info("orchestra_memory listening on %s:%s", service.config.host, service.config.port)
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        raise
    finally:
        await runner.cleanup()
        await service.stop()
