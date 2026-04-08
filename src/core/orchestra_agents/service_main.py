"""CLI entrypoint for the orchestra_agents lifecycle service."""

from __future__ import annotations

import asyncio
import logging
import os

from aiohttp import web

from core.orchestra_agents.manifest import AgentManifest
from core.orchestra_agents.service import OrchestraAgentsService, build_app


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


async def _build_runner() -> tuple[web.AppRunner, OrchestraAgentsService]:
    service = OrchestraAgentsService.create()
    runner = web.AppRunner(build_app(service))
    await runner.setup()
    return runner, service


async def _auto_start_one(
    service: OrchestraAgentsService,
    manifest: AgentManifest,
    logger: logging.Logger,
) -> bool:
    logger.info("auto-start attempt slug=%s", manifest.slug)
    try:
        await service.start_agent(manifest.slug)
    except Exception:
        logger.exception("auto-start failed slug=%s", manifest.slug)
        return False
    logger.info("auto-start success slug=%s", manifest.slug)
    return True


async def _auto_start_agents(service: OrchestraAgentsService) -> None:  # noqa: WPS476 — agents must start sequentially to avoid resource contention
    logger = logging.getLogger(__name__)
    eligible = service.state.registry.auto_start_manifests()
    logger.info("auto-start pass started eligible=%d", len(eligible))
    ok_count = 0
    for manifest in eligible:
        if await _auto_start_one(service, manifest, logger):  # noqa: WPS476
            ok_count += 1
    logger.info(
        "auto-start pass complete total=%d ok=%d failed=%d",
        len(eligible),
        ok_count,
        len(eligible) - ok_count,
    )


async def _run() -> None:
    runner, service = await _build_runner()
    host = str(os.getenv("ORCHESTRA_AGENTS_HOST") or "0.0.0.0")
    port = int(os.getenv("ORCHESTRA_AGENTS_PORT") or "8790")
    await web.TCPSite(runner, host=host, port=port).start()
    logging.getLogger(__name__).info(
        "orchestra_agents listening on %s:%s (manifests_root=%s)",
        host,
        port,
        service.state.registry.manifests_root,
    )
    asyncio.get_running_loop().create_task(_auto_start_agents(service))
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
