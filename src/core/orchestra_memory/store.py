from __future__ import annotations

import asyncio
import hashlib
from importlib import import_module
from pathlib import Path
from typing import Any, cast

from core.orchestra_memory.store_rows import (
    SearchRequest,
    StoreRules,
)
from core.orchestra_memory.store_types import MempalaceClient, MempalaceCollection, MempalaceConfig

_READ_INCLUDE = ("documents", "metadatas")


def _read_include() -> list[str]:
    return list(_READ_INCLUDE)


class _StoreLifecycleOps:
    _storage_path: Path
    _collection: MempalaceCollection | None
    _started: bool

    async def start(self) -> None:
        if self._started:
            return
        self._storage_path.mkdir(parents=True, exist_ok=True)
        self._collection = _create_collection(self._storage_path)
        self._started = True

    async def close(self) -> None:
        if not self._started:
            return
        self._collection = None
        self._started = False

    async def ping(self) -> bool:
        return self._started

    def _collection_required(self) -> MempalaceCollection:
        if self._collection is None:
            raise RuntimeError("store is not started")
        return self._collection


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
                include=_read_include(),
            )
        return request.matches(payload)


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
            self._collection_required().add(
                ids=[item["memory_id"]],
                documents=[item["text"]],
                metadatas=[self._rules.metadata_from_item(item)],
                embeddings=[_embedding_for_text(item["text"])],
            )
        return item

    async def delete(self, *, agent_slug: str, memory_id: str) -> bool:
        filters = self._rules.scoped_filters(agent_slug=agent_slug, room=None, category=None)
        request = SearchRequest(filters=filters, query="", limit=1)
        async with self._lock:
            payload = self._collection_required().get(ids=[memory_id], include=_read_include())
            if not request.matches(payload):
                return False
            self._collection_required().delete(ids=[memory_id])
        return True

    async def clear(self, *, agent_slug: str, room: str | None, category: str | None) -> int:
        request = self._rules.build_search_request(
            agent_slug=agent_slug,
            query="",
            room=room,
            category=category,
            limit=100,
        )
        async with self._lock:
            payload = self._collection_required().get(
                where=request.filters.to_where(),
                include=_read_include(),
            )
            ids = [item["memory_id"] for item in request.matches(payload)]
            if ids:
                self._collection_required().delete(ids=ids)
        return len(ids)


class OrchestraMemoryStore(_StoreReadOps, _StoreWriteOps):
    def __init__(
        self,
        *,
        storage_path: Path,
        allowed_rooms: tuple[str, ...],
        allowed_categories: tuple[str, ...],
    ) -> None:
        self._storage_path = storage_path
        self._rules = StoreRules(
            allowed_rooms=set(allowed_rooms),
            allowed_categories=set(allowed_categories),
        )
        self._lock = asyncio.Lock()
        self._collection: MempalaceCollection | None = None
        self._started = False


def _create_collection(storage_path: Path) -> MempalaceCollection:
    mempalace_config = cast(Any, import_module("mempalace.config"))
    chromadb = cast(Any, import_module("chromadb"))
    config = cast(MempalaceConfig, mempalace_config.MempalaceConfig())
    client = cast(MempalaceClient, chromadb.PersistentClient(path=str(storage_path)))
    return client.get_or_create_collection(config.collection_name)


def _embedding_for_text(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [byte / 255.0 for byte in digest]
