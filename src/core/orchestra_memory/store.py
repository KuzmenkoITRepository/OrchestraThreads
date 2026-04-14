from __future__ import annotations

import asyncio
from importlib import import_module as _import_module
from pathlib import Path

from core.orchestra_memory.store_lifecycle import _StoreLifecycleOps
from core.orchestra_memory.store_reads import _StoreReadOps
from core.orchestra_memory.store_rows import StoreRules
from core.orchestra_memory.store_types import MempalaceCollection
from core.orchestra_memory.store_writes import _StoreWriteOps


def import_module(module_name: str) -> object:
    return _import_module(module_name)


class OrchestraMemoryStore(_StoreReadOps, _StoreWriteOps, _StoreLifecycleOps):
    def __init__(
        self,
        *,
        storage_path: Path,
        rules: StoreRules | None = None,
    ) -> None:
        self._storage_path = storage_path
        self._rules = rules or StoreRules()
        self._lock = asyncio.Lock()
        self._collection: MempalaceCollection | None = None
        self._started = False
