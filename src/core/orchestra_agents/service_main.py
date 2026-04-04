"""CLI entrypoint for the orchestra_agents lifecycle service."""

from __future__ import annotations

import asyncio
import logging
import os

from aiohttp import web

from .service import OrchestraAgentsService, build_app


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


async def _run() -> None:
    service = OrchestraAgentsService()
    app = build_app(service)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(
        runner,
        host=str(os.getenv("ORCHESTRA_AGENTS_HOST") or "0.0.0.0"),
        port=int(os.getenv("ORCHESTRA_AGENTS_PORT", "8790")),
    )
    await site.start()
    logging.getLogger(__name__).info(
        "orchestra_agents listening on %s:%s (manifests_root=%s)",
        os.getenv("ORCHESTRA_AGENTS_HOST", "0.0.0.0"),
        os.getenv("ORCHESTRA_AGENTS_PORT", "8790"),
        service.registry.manifests_root,
    )
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()


def main() -> None:
    configure_logging()
    asyncio.run(_run())


if __name__ == "__main__":
    main()
