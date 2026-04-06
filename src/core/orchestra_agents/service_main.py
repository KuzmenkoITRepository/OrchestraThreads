"""CLI entrypoint for the orchestra_agents lifecycle service."""

from __future__ import annotations

import asyncio
import logging
import os

from aiohttp import web

from core.orchestra_agents.service import OrchestraAgentsService, build_app


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


async def _build_runner() -> tuple[web.AppRunner, OrchestraAgentsService]:
    service = OrchestraAgentsService()
    runner = web.AppRunner(build_app(service))
    await runner.setup()
    return runner, service


async def _run() -> None:
    runner, service = await _build_runner()
    host = str(os.getenv("ORCHESTRA_AGENTS_HOST") or "0.0.0.0")
    port = int(os.getenv("ORCHESTRA_AGENTS_PORT") or "8790")
    await web.TCPSite(runner, host=host, port=port).start()
    logging.getLogger(__name__).info(
        "orchestra_agents listening on %s:%s (manifests_root=%s)",
        host,
        port,
        service.registry.manifests_root,
    )
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        raise
    finally:
        await runner.cleanup()


def main() -> None:
    configure_logging()
    asyncio.run(_run())


if __name__ == "__main__":
    main()
