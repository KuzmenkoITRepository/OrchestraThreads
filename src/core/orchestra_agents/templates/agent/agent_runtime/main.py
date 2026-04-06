"""Template runtime entrypoint for __AGENT_SLUG__."""

from __future__ import annotations

import asyncio
import logging
import os

from core.orchestra_agents.runtime import StandardAgentApplication
from core.orchestra_agents.templates.agent.agent_runtime.backend import TemplateBackend


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


async def _run() -> None:
    backend = TemplateBackend(
        agent_slug=str(os.getenv("ORCHESTRA_AGENT_SLUG") or "__AGENT_SLUG__").strip()
        or "__AGENT_SLUG__",
        backend_type=str(os.getenv("ORCHESTRA_AGENT_BACKEND_TYPE") or "__BACKEND_TYPE__").strip()
        or "__BACKEND_TYPE__",
        working_dir=str(os.getenv("ORCHESTRA_AGENT_WORKING_DIR") or "/workspace").strip()
        or "/workspace",
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
