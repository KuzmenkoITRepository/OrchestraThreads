from __future__ import annotations

import asyncio
import logging

from aiohttp import web

from core.orchestra_memory.service_app import build_memory_app
from core.orchestra_memory.service_lifecycle import OrchestraMemoryService

logger = logging.getLogger(__name__)


async def start_service_site(service: OrchestraMemoryService) -> web.AppRunner:
    runner = web.AppRunner(build_memory_app(service))
    await runner.setup()
    site = web.TCPSite(runner, host=service.config.host, port=service.config.port)
    await site.start()
    return runner


async def run_memory_service() -> None:
    service = OrchestraMemoryService()
    await service.start()
    runner = await start_service_site(service)
    logger.info("orchestra_memory listening on %s:%s", service.config.host, service.config.port)
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        raise
    finally:
        await runner.cleanup()
        await service.stop()
