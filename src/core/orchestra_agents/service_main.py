"""CLI entrypoint for the orchestra_agents lifecycle service."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, cast

from aiohttp import web

from core.orchestra_agents.manifest import AgentManifest
from core.orchestra_agents.service import OrchestraAgentsService, build_app


class _ServiceProtocol:
    state: Any

    @classmethod
    def create(cls) -> Any: ...

    async def start_agent(self, slug: str) -> Any: ...


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


class _ServiceRuntimeFacade:
    @staticmethod
    def service_class() -> type[Any]:
        return OrchestraAgentsService

    @staticmethod
    def build_app(service: _ServiceProtocol) -> web.Application:
        return build_app(cast(OrchestraAgentsService, service))


class _ServiceBootstrap:
    @staticmethod
    def listen_host() -> str:
        return str(os.getenv("ORCHESTRA_AGENTS_HOST") or "0.0.0.0")

    @staticmethod
    def listen_port() -> int:
        return int(os.getenv("ORCHESTRA_AGENTS_PORT") or "8790")

    @staticmethod
    def log_listening(service: _ServiceProtocol, *, host: str, port: int) -> None:
        logging.getLogger(__name__).info(
            "orchestra_agents listening on %s:%s (manifests_root=%s)",
            host,
            port,
            service.state.registry.manifests_root,
        )

    @staticmethod
    async def start_site(runner: web.AppRunner, *, host: str, port: int) -> None:
        await web.TCPSite(runner, host=host, port=port).start()

    @staticmethod
    async def build_runner() -> tuple[web.AppRunner, _ServiceProtocol]:
        service = cast(_ServiceProtocol, _ServiceRuntimeFacade.service_class().create())
        runner = web.AppRunner(_ServiceRuntimeFacade.build_app(service))
        await runner.setup()
        return runner, service


class _AutoStartLoop:
    @staticmethod
    async def start_one(
        service: _ServiceProtocol,
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

    @classmethod
    async def start_agents(
        cls,
        service: _ServiceProtocol,
    ) -> None:  # noqa: WPS476 — agents must start sequentially to avoid resource contention
        logger = logging.getLogger(__name__)
        eligible = service.state.registry.auto_start_manifests()
        logger.info("auto-start pass started eligible=%d", len(eligible))
        ok_count = 0
        for manifest in eligible:
            if await cls.start_one(service, manifest, logger):  # noqa: WPS476
                ok_count += 1
        logger.info(
            "auto-start pass complete total=%d ok=%d failed=%d",
            len(eligible),
            ok_count,
            len(eligible) - ok_count,
        )

    @classmethod
    def schedule(cls, service: _ServiceProtocol) -> None:
        asyncio.get_running_loop().create_task(cls.start_agents(service))


async def _run() -> None:
    runner, service = await _ServiceBootstrap.build_runner()
    host = _ServiceBootstrap.listen_host()
    port = _ServiceBootstrap.listen_port()
    await _ServiceBootstrap.start_site(runner, host=host, port=port)
    _ServiceBootstrap.log_listening(service, host=host, port=port)
    _AutoStartLoop.schedule(service)
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
