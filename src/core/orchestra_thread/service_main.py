"""CLI entrypoint for running the OrchestraThreads MVP service."""

from __future__ import annotations

import asyncio
import logging
import os

from aiohttp import web

from core.orchestra_thread.service_runtime import OrchestraThreadsService, build_app
from core.orchestra_thread.service_runtime_config import RuntimeConfigOverrides


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


async def _start_site(runner: web.AppRunner) -> tuple[str, int]:
    host = str(os.getenv("ORCHESTRA_THREADS_HOST") or "0.0.0.0")
    port = int(os.getenv("ORCHESTRA_THREADS_PORT") or "8788")
    await web.TCPSite(runner, host=host, port=port).start()
    return host, port


def _log_started(service: OrchestraThreadsService, host: str, port: int) -> None:
    logging.getLogger(__name__).info(
        "OrchestraThreads listening on %s:%s (schema=%s)",
        host,
        port,
        service.database_schema,
    )


async def _stop_runtime(runner: web.AppRunner, service: OrchestraThreadsService) -> None:
    await runner.cleanup()
    await service.stop()


async def _run() -> None:
    service = OrchestraThreadsService(runtime_config_overrides=RuntimeConfigOverrides())
    await service.start()
    app = build_app(service)
    runner = web.AppRunner(app)
    await runner.setup()
    host, port = await _start_site(runner)
    _log_started(service, host, port)
    try:
        await asyncio.Event().wait()
    except BaseException:
        return
    finally:
        await _stop_runtime(runner, service)


def main() -> None:
    configure_logging()
    asyncio.run(_run())


if __name__ == "__main__":
    main()
