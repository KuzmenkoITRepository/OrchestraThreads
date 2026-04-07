"""Thread service integration — registration, heartbeat, MCP server, guide loading."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from agents.sgr.agent_runtime.support.settings import (
    SGRRuntimeSettings,
    thread_client_timeout_seconds,
)
from core.orchestra_thread.client import OrchestraThreadsClient
from core.orchestra_thread.mcp_server import OrchestraThreadsMCPServer

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _AgentMetadata:
    backend_type: str
    route_policy: str
    model: str


def _registration_enabled(settings: SGRRuntimeSettings) -> bool:
    return bool(settings.threads_url and settings.http_endpoint)


def _build_client(
    settings: SGRRuntimeSettings,
    llm_timeout: float | None,
) -> OrchestraThreadsClient:
    if not settings.threads_url:
        raise RuntimeError("ORCHESTRA_THREADS_URL is required for thread operations")
    return OrchestraThreadsClient(
        base_url=settings.threads_url,
        timeout_seconds=thread_client_timeout_seconds(llm_timeout),
    )


class SGRThreadOps:
    """Manages thread service registration, heartbeat, and MCP server."""

    def __init__(
        self,
        agent_slug: str,
        settings: SGRRuntimeSettings,
        llm_timeout_seconds: float | None,
        metadata: _AgentMetadata,
    ) -> None:
        self.agent_slug = agent_slug
        self._settings = settings
        self._llm_timeout = llm_timeout_seconds
        self._metadata = metadata
        self.thread_client: OrchestraThreadsClient | None = None
        self.mcp_server: OrchestraThreadsMCPServer | None = None
        self.registered = False
        self.guide_loaded = False
        self.guide_text: str = ""
        self._heartbeat_task: asyncio.Task[None] | None = None

    def ensure_client(self) -> OrchestraThreadsClient:
        if self.thread_client is None:
            self.thread_client = _build_client(self._settings, self._llm_timeout)
        return self.thread_client

    def ensure_mcp_server(self) -> OrchestraThreadsMCPServer:
        if self.mcp_server is None:
            self.mcp_server = OrchestraThreadsMCPServer(
                agent_slug=self.agent_slug, client=self.ensure_client()
            )
        return self.mcp_server

    async def ensure_registered(self) -> None:
        if self.registered:
            return
        if not _registration_enabled(self._settings):
            return
        await _register_agent(self)
        self.registered = True
        if self._heartbeat_task is None:
            self._heartbeat_task = asyncio.create_task(
                self._heartbeat_loop(), name=f"{self.agent_slug}-heartbeat"
            )

    async def refresh_guide(self) -> None:
        if self.guide_loaded:
            return
        if not self._settings.threads_url:
            return
        try:
            payload = await self.ensure_client().get_instruction(
                view=self._settings.guide_view, section="mcp"
            )
        except Exception as exc:
            logger.warning("failed to fetch OrchestraThreads guide: %s", exc)
            return
        instruction = payload.get("instruction") if isinstance(payload, dict) else None
        if isinstance(instruction, dict):
            self.guide_text = str(instruction.get("text") or "").strip()
        self.guide_loaded = True

    async def shutdown(self) -> None:
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                logger.debug("heartbeat task cancelled for %s", self.agent_slug)
            finally:
                self._heartbeat_task = None
        if self.mcp_server is not None:
            await self.mcp_server.close()
            self.mcp_server = None
            self.thread_client = None
            return
        if self.thread_client is not None:
            await self.thread_client.close()
            self.thread_client = None

    async def _heartbeat_loop(self) -> None:
        while True:
            await _heartbeat_tick(self)


async def _heartbeat_tick(ops: SGRThreadOps) -> None:
    try:
        await asyncio.sleep(ops._settings.heartbeat_interval_seconds)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("heartbeat sleep failed for %s: %s", ops.agent_slug, exc)
        return
    if not ops.registered:
        return
    try:
        await ops.ensure_client().heartbeat(agent_slug=ops.agent_slug)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("heartbeat failed for %s: %s", ops.agent_slug, exc)
        if _registration_enabled(ops._settings):
            await _try_reregister(ops)


async def _try_reregister(ops: SGRThreadOps) -> None:
    try:
        await _register_agent(ops)
    except Exception as exc:
        logger.warning("re-register failed for %s: %s", ops.agent_slug, exc)
        return
    ops.registered = True


async def _register_agent(ops: SGRThreadOps) -> None:
    await ops.ensure_client().register_agent(
        agent_slug=ops.agent_slug,
        display_name=ops.agent_slug,
        base_url=ops._settings.http_endpoint,
        metadata={
            "kind": "sgr-minimax-tool-agent",
            "backend_type": ops._metadata.backend_type,
            "route_policy": ops._metadata.route_policy,
            "model": ops._metadata.model,
            "tool_surface": "orchestra-threads-mcp",
        },
    )
