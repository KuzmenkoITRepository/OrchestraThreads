from __future__ import annotations

import asyncio

from core.orchestra_memory.store_collection import embedding_for_text
from core.orchestra_memory.store_lifecycle import _StoreLifecycleOps
from core.orchestra_memory.store_rows import StoreRules


class _StoreWriteOps(_StoreLifecycleOps):
    _lock: asyncio.Lock
    _rules: StoreRules

    async def remember(
        self,
        *,
        agent_slug: str,
        room: str,
        category: str,
        text: str,
    ) -> dict[str, str]:
        item = self._rules.build_item(
            agent_slug=agent_slug,
            room=room,
            category=category,
            text=text,
        )
        async with self._lock:
            metadata = self._rules.metadata_from_item(item)
            metadata["text"] = item["text"]
            self._collection_required().add(
                ids=[item["memory_id"]],
                documents=[item["text"]],
                metadatas=[metadata],
                embeddings=[embedding_for_text(item["text"])],
            )
        return item

    async def delete(self, *, agent_slug: str, memory_id: str) -> bool:
        filters = self._rules.scoped_filters(agent_slug=agent_slug, room=None, category=None)
        async with self._lock:
            payload = self._collection_required().get(
                ids=[memory_id],
                where=filters.to_where(),
                include=[],
            )
            ids = payload.get("ids", [])
            if not isinstance(ids, list) or not ids:
                return False
            self._collection_required().delete(ids=[memory_id])
        return True

    async def clear(self, *, agent_slug: str, room: str | None, category: str | None) -> int:
        filters = self._rules.scoped_filters(agent_slug=agent_slug, room=room, category=category)
        async with self._lock:
            payload = self._collection_required().get(
                where=filters.to_where(),
                include=[],
            )
            ids = payload.get("ids", [])
            if not isinstance(ids, list):
                return 0
            scoped_ids = [memory_id for memory_id in ids if isinstance(memory_id, str)]
            if not scoped_ids:
                return 0
            self._collection_required().delete(ids=scoped_ids)
        return len(scoped_ids)
