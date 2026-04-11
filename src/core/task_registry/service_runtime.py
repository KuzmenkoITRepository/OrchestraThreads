"""HTTP runtime for the task registry service."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from core.task_registry.config import TaskRegistryConfig, load_config
from core.task_registry.service_runtime_web import setup_app, start_site, stop_service

logger = logging.getLogger(__name__)


@dataclass
class TaskRegistryStore:
    """Placeholder task registry store."""

    database_url: str
    running: bool = False

    async def start(self) -> None:
        self.running = True

    async def close(self) -> None:
        self.running = False

    async def ping(self) -> bool:
        return self.running


class TaskRegistryService:
    """Task registry HTTP service."""

    def __init__(self, config: TaskRegistryConfig | None = None) -> None:
        self.config = config or load_config()
        self.store = TaskRegistryStore(self.config.database_url)
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


async def run_service() -> None:
    service = TaskRegistryService()
    await service.start()
    runner = await setup_app(service)
    await start_site(runner, service.config)
    logger.info("Task registry listening on %s:%s", service.config.host, service.config.port)
    try:
        await asyncio.Event().wait()
    except BaseException:
        return
    finally:
        await stop_service(service, runner)
