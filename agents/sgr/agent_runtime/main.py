"""Runtime entrypoint for the SGR Minimax example agent."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from core.orchestra_agents.manifest import AgentManifest
from core.orchestra_agents.runtime import StandardAgentApplication

from agents.sgr.agent_runtime.backend import SGRMinimaxBackend


@dataclass(frozen=True)
class _RuntimeConfig:
    slug: str
    backend_type: str
    working_dir: str
    system_prompt: str
    http_endpoint: str | None
    host: str
    port: int


def _resolve_field(
    env_key: str,
    fields: dict[str, str],
    field: str,
    default: str,
) -> str:
    env_value = os.getenv(env_key)
    raw = str(env_value or fields.get(field) or default).strip()
    return raw or default


def _resolve_runtime_config(manifest: AgentManifest | None) -> _RuntimeConfig:
    fields: dict[str, str] = (
        {}
        if manifest is None
        else {
            "slug": str(manifest.slug).strip(),
            "backend_type": str(manifest.backend.type).strip(),
            "working_dir": str(manifest.agent.working_dir).strip(),
        }
    )
    return _RuntimeConfig(
        slug=_resolve_field("ORCHESTRA_AGENT_SLUG", fields, "slug", "sgr"),
        backend_type=_resolve_field(
            "ORCHESTRA_AGENT_BACKEND_TYPE",
            fields,
            "backend_type",
            "sgr_minimax",
        ),
        working_dir=_resolve_field(
            "ORCHESTRA_AGENT_WORKING_DIR",
            fields,
            "working_dir",
            "/workspace/agents/sgr",
        ),
        system_prompt=manifest.load_system_prompt() if manifest else "",
        http_endpoint=str(os.getenv("ORCHESTRA_AGENT_HTTP_ENDPOINT") or "").strip() or None,
        host=str(os.getenv("AGENT_HTTP_HOST") or "0.0.0.0").strip() or "0.0.0.0",
        port=int(os.getenv("AGENT_HTTP_PORT", "8787")),
    )


def configure_logging() -> None:
    log_level = str(os.getenv("LOG_LEVEL") or "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
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
    config = _resolve_runtime_config(manifest)
    manifest_backend_config = {} if manifest is None else dict(manifest.backend.config)
    if config.http_endpoint:
        manifest_backend_config.setdefault("http_endpoint", config.http_endpoint)
    backend = SGRMinimaxBackend(
        agent_slug=config.slug,
        backend_type=config.backend_type,
        working_dir=config.working_dir,
        config=manifest_backend_config,
        system_prompt=config.system_prompt,
    )
    app = StandardAgentApplication(
        backend=backend,
        host=config.host,
        port=config.port,
    )
    await app.serve_forever()


def main() -> None:
    configure_logging()
    asyncio.run(_run())


if __name__ == "__main__":
    main()
