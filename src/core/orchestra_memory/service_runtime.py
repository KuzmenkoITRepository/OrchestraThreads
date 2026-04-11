from __future__ import annotations

from aiohttp import web

from core.orchestra_memory.service_app import build_memory_app
from core.orchestra_memory.service_lifecycle import (
    OrchestraMemoryService as OrchestraMemoryService,
)
from core.orchestra_memory.service_runner import run_memory_service


def build_app(service: OrchestraMemoryService) -> web.Application:
    return build_memory_app(service)


async def run_service() -> None:
    await run_memory_service()
