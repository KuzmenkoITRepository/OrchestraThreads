from __future__ import annotations

from core.orchestra_memory.config import OrchestraMemoryConfig, load_config
from core.orchestra_memory.service_ops import _ServiceOperations
from core.orchestra_memory.store import OrchestraMemoryStore


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
