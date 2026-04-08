"""Runtime entrypoint for the SGR Minimax example agent."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from agents.sgr.agent_runtime.backend import SGRMinimaxBackend
from agents.sgr.agent_runtime.runtime_config import RuntimeConfig, resolve_runtime_config
from core.orchestra_agents.manifest import AgentManifest
from core.orchestra_agents.runtime import StandardAgentApplication


def configure_logging() -> None:
    """Configure root logging from environment."""
    log_level = str(os.getenv("LOG_LEVEL") or "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def load_manifest() -> AgentManifest | None:
    """Load agent manifest from path specified in environment."""
    raw_path = str(os.getenv("ORCHESTRA_AGENT_MANIFEST") or "").strip()
    if not raw_path:
        return None
    manifest_path = Path(raw_path)
    if not manifest_path.exists():
        return None
    return AgentManifest.from_file(manifest_path)


async def _run() -> None:
    manifest = load_manifest()
    config = resolve_runtime_config(manifest)
    raw_backend = {} if manifest is None else dict(manifest.backend.config)
    backend = _create_backend(config, raw_backend)
    app = StandardAgentApplication(backend=backend, host=config.host, port=config.port)
    await app.serve_forever()


def _create_backend(
    config: RuntimeConfig,
    raw_backend: dict[str, object],
) -> SGRMinimaxBackend:
    """Create and configure the SGR backend with MCP tools."""
    from agents.sgr.agent_runtime import mcp_loader
    from agents.sgr.agent_runtime.backend import configure_mcp_tools

    backend = SGRMinimaxBackend(
        agent_slug=config.slug,
        backend_type=config.backend_type,
        working_dir=config.working_dir,
        config=raw_backend,
        system_prompt=config.system_prompt,
    )
    backend.http_endpoint = os.getenv("ORCHESTRA_AGENT_HTTP_ENDPOINT")
    servers, schemas = mcp_loader.load_mcp_from_config(dict(raw_backend))
    if servers:
        configure_mcp_tools(backend, servers, tool_schemas=schemas)
    return backend


def main() -> None:
    """Start the SGR agent runtime."""
    configure_logging()
    asyncio.run(_run())


if __name__ == "__main__":
    main()
