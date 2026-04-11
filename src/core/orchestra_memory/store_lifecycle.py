from __future__ import annotations

from pathlib import Path

from core.orchestra_memory.store_collection import create_collection
from core.orchestra_memory.store_types import MempalaceCollection


class _StoreLifecycleOps:
    _storage_path: Path
    _collection: MempalaceCollection | None
    _started: bool

    async def start(self) -> None:
        if self._started:
            return
        self._storage_path.mkdir(parents=True, exist_ok=True)
        self._collection = create_collection(self._storage_path)
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
