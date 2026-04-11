from __future__ import annotations

from core.orchestra_memory.store import OrchestraMemoryStore


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
