from __future__ import annotations

import asyncio

from core.orchestra_memory.store_collection import read_include
from core.orchestra_memory.store_lifecycle import _StoreLifecycleOps
from core.orchestra_memory.store_rows import StoreRules


class _StoreReadOps(_StoreLifecycleOps):
    _lock: asyncio.Lock
    _rules: StoreRules

    async def search(
        self,
        *,
        agent_slug: str,
        query: str,
        room: str | None,
        category: str | None,
        limit: int,
    ) -> list[dict[str, str]]:
        request = self._rules.build_search_request(
            agent_slug=agent_slug,
            query=query,
            room=room,
            category=category,
            limit=limit,
        )
        async with self._lock:
            payload = self._collection_required().get(
                where=request.filters.to_where(),
                include=read_include(),
            )
        return request.matches(payload)
