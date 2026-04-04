"""CLI entrypoint for running the OrchestraThreads MVP service."""

from __future__ import annotations

import asyncio
import logging
import os

from aiohttp import web

from .service import OrchestraThreadsService, build_app


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


async def _run() -> None:
    service = OrchestraThreadsService()
    await service.start()
    app = build_app(service)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(
        runner,
        host=str(os.getenv("ORCHESTRA_THREADS_HOST") or "0.0.0.0"),
        port=int(os.getenv("ORCHESTRA_THREADS_PORT", "8788")),
    )
    await site.start()
    logging.getLogger(__name__).info(
        "OrchestraThreads listening on %s:%s (schema=%s)",
        os.getenv("ORCHESTRA_THREADS_HOST", "0.0.0.0"),
        os.getenv("ORCHESTRA_THREADS_PORT", "8788"),
        service.database_schema,
    )
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
        await service.stop()


def main() -> None:
    configure_logging()
    asyncio.run(_run())


if __name__ == "__main__":
    main()
