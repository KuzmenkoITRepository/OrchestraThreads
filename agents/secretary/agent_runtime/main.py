"""Template runtime entrypoint for the agent_mux Orchestra agent template."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from core.orchestra_agents.manifest import AgentManifest
from core.orchestra_agents.runtime import StandardAgentApplication

from .backend import AgentMuxBackend


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def load_manifest() -> AgentManifest | None:
    raw_path = str(os.getenv("ORCHESTRA_AGENT_MANIFEST") or "").strip()
    if not raw_path:
        return None
    manifest_path = Path(raw_path)
    if not manifest_path.exists():
        return None
    return AgentManifest.from_file(manifest_path)


async def _run() -> None:
    manifest = load_manifest()
    manifest_backend_config = manifest.backend.config if manifest is not None else {}
    working_dir = (
        str(os.getenv("ORCHESTRA_AGENT_WORKING_DIR") or (manifest.agent.working_dir if manifest else "/workspace/agents/__AGENT_SLUG__")).strip()
        or "/workspace/agents/__AGENT_SLUG__"
    )
    backend = AgentMuxBackend(
        agent_slug=str(os.getenv("ORCHESTRA_AGENT_SLUG") or (manifest.slug if manifest else "__AGENT_SLUG__")).strip() or "__AGENT_SLUG__",
        backend_type=(
            str(os.getenv("ORCHESTRA_AGENT_BACKEND_TYPE") or (manifest.backend.type if manifest else "__BACKEND_TYPE__")).strip()
            or "__BACKEND_TYPE__"
        ),
        working_dir=working_dir,
        config=manifest_backend_config,
        system_prompt=manifest.load_system_prompt() if manifest is not None else "",
        http_endpoint=str(os.getenv("ORCHESTRA_AGENT_HTTP_ENDPOINT") or "").strip() or None,
    )
    app = StandardAgentApplication(
        backend=backend,
        host=str(os.getenv("AGENT_HTTP_HOST") or "0.0.0.0").strip() or "0.0.0.0",
        port=int(os.getenv("AGENT_HTTP_PORT", "8787")),
    )
    await app.serve_forever()


def main() -> None:
    configure_logging()
    asyncio.run(_run())


if __name__ == "__main__":
    main()
