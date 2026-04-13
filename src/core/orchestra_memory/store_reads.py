from __future__ import annotations

import asyncio

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
            collection = self._collection_required()
        payload = collection.get(where={"wing": agent_slug}, include=["metadatas", "documents"])
        return request.matches(payload)

    async def list_rooms(self, *, agent_slug: str) -> list[str]:
        """Return all unique room names used by this agent."""
        async with self._lock:
            collection = self._collection_required()
        payload = collection.get(where={"wing": agent_slug}, include=["metadatas"])
        rooms: set[str] = set()
        metadatas = payload.get("metadatas", [])
        if isinstance(metadatas, list):
            for metadata in metadatas:
                if isinstance(metadata, dict) and "room" in metadata:
                    rooms.add(str(metadata["room"]))
        return sorted(rooms)

    async def list_categories(self, *, agent_slug: str) -> list[str]:
        """Return all unique category names used by this agent."""
        async with self._lock:
            collection = self._collection_required()
        payload = collection.get(where={"wing": agent_slug}, include=["metadatas"])
        categories: set[str] = set()
        metadatas = payload.get("metadatas", [])
        if isinstance(metadatas, list):
            for metadata in metadatas:
                if isinstance(metadata, dict) and "category" in metadata:
                    categories.add(str(metadata["category"]))
        return sorted(categories)
