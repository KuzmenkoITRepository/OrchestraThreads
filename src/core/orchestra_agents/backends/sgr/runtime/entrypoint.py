"""Runtime entrypoint internals for the canonical SGR backend."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from core.orchestra_agents.backends.sgr.backend import SGRMinimaxBackend
from core.orchestra_agents.runtime import (
    configure_logging,
    serve_backend,
)

_WORKING_DIR_FALLBACK = "/workspace/agents/sgr"
_AGENT_SLUG_FALLBACK = "sgr"
_BACKEND_TYPE_FALLBACK = "sgr_minimax"


@dataclass(frozen=True)
class _BackendInit:
    agent_slug: str
    backend_type: str
    working_dir: str
    config: dict[str, object]


async def _run() -> None:
    await serve_backend(
        backend_factory=_create_backend,
        working_dir_fallback=_WORKING_DIR_FALLBACK,
        agent_slug_fallback=_AGENT_SLUG_FALLBACK,
        backend_type_fallback=_BACKEND_TYPE_FALLBACK,
    )


def _create_backend(
    *,
    system_prompt: str,
    http_endpoint: str | None = None,
    **kwargs: object,
) -> SGRMinimaxBackend:
    """Create and configure the SGR backend with MCP tools."""
    from core.orchestra_agents.backends.sgr import mcp_loader
    from core.orchestra_agents.backends.sgr.backend import configure_mcp_tools

    init = _build_backend_init(kwargs)
    backend = SGRMinimaxBackend(
        agent_slug=init.agent_slug,
        backend_type=init.backend_type,
        working_dir=init.working_dir,
        config=init.config,
        system_prompt=system_prompt,
    )
    backend.http_endpoint = http_endpoint
    servers, schemas = mcp_loader.load_mcp_from_config(dict(init.config))
    if servers:
        configure_mcp_tools(backend, servers, tool_schemas=schemas)
    return backend


def _build_backend_init(kwargs: dict[str, object]) -> _BackendInit:
    raw_config = kwargs["config"]
    return _BackendInit(
        agent_slug=str(kwargs["agent_slug"]),
        backend_type=str(kwargs["backend_type"]),
        working_dir=str(kwargs["working_dir"]),
        config=_normalize_config(raw_config),
    )


def _normalize_config(raw_config: object) -> dict[str, object]:
    if not isinstance(raw_config, dict):
        return {}
    return {str(key): value for key, value in raw_config.items()}


def main() -> None:
    """Start the SGR agent runtime."""
    configure_logging()
    asyncio.run(_run())
