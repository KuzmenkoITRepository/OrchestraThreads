"""Shared bootstrap helpers for manifest-driven agent runtimes."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable
from pathlib import Path

from core.orchestra_agents.manifest import AgentManifest
from core.orchestra_agents.runtime.app import StandardAgentApplication
from core.orchestra_agents.runtime.backend import BaseAgentBackend


def configure_logging() -> None:
    """Configure default runtime logging from environment variables."""

    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def load_manifest() -> AgentManifest | None:
    """Load the optional runtime manifest configured via environment."""

    raw_path = str(os.getenv("ORCHESTRA_AGENT_MANIFEST") or "").strip()
    if not raw_path:
        return None
    manifest_path = Path(raw_path)
    if not manifest_path.exists():
        return None
    return AgentManifest.from_file(manifest_path)


def resolve_working_dir(manifest: AgentManifest | None, *, fallback: str) -> str:
    """Resolve the runtime working directory from env or manifest."""

    configured_dir = os.getenv("ORCHESTRA_AGENT_WORKING_DIR")
    if configured_dir is not None:
        return str(configured_dir).strip() or fallback
    if manifest is None:
        return fallback
    return str(manifest.agent.working_dir).strip() or fallback


def resolve_agent_slug(manifest: AgentManifest | None, *, fallback: str) -> str:
    """Resolve the agent slug from env or manifest."""

    configured_slug = os.getenv("ORCHESTRA_AGENT_SLUG")
    if configured_slug is not None:
        return str(configured_slug).strip() or fallback
    if manifest is None:
        return fallback
    return str(manifest.slug).strip() or fallback


def resolve_backend_type(manifest: AgentManifest | None, *, fallback: str) -> str:
    """Resolve the backend type from env or manifest."""

    configured_backend_type = os.getenv("ORCHESTRA_AGENT_BACKEND_TYPE")
    if configured_backend_type is not None:
        return str(configured_backend_type).strip() or fallback
    if manifest is None:
        return fallback
    return str(manifest.backend.type).strip() or fallback


async def serve_backend(
    *,
    backend_factory: Callable[..., BaseAgentBackend],
    working_dir_fallback: str,
    agent_slug_fallback: str,
    backend_type_fallback: str,
) -> None:
    """Build a backend instance from manifest/env configuration and serve it."""

    manifest = load_manifest()
    backend_config = {} if manifest is None else dict(manifest.backend.config)
    system_prompt = "" if manifest is None else manifest.load_system_prompt()
    backend = backend_factory(
        agent_slug=resolve_agent_slug(manifest, fallback=agent_slug_fallback),
        backend_type=resolve_backend_type(manifest, fallback=backend_type_fallback),
        working_dir=resolve_working_dir(manifest, fallback=working_dir_fallback),
        config=backend_config,
        system_prompt=system_prompt,
        http_endpoint=str(os.getenv("ORCHESTRA_AGENT_HTTP_ENDPOINT") or "").strip() or None,
    )
    app = StandardAgentApplication(
        backend=backend,
        host=str(os.getenv("AGENT_HTTP_HOST") or "0.0.0.0").strip() or "0.0.0.0",
        port=int(os.getenv("AGENT_HTTP_PORT", "8787")),
    )
    await app.serve_forever()


def run_backend(
    *,
    backend_factory: Callable[..., BaseAgentBackend],
    working_dir_fallback: str,
    agent_slug_fallback: str,
    backend_type_fallback: str,
) -> None:
    """Configure logging and run a backend forever."""

    configure_logging()
    asyncio.run(
        serve_backend(
            backend_factory=backend_factory,
            working_dir_fallback=working_dir_fallback,
            agent_slug_fallback=agent_slug_fallback,
            backend_type_fallback=backend_type_fallback,
        )
    )
