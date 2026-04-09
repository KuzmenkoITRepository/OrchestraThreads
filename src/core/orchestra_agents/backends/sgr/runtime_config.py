"""Runtime configuration resolution for the SGR agent."""

from __future__ import annotations

import os
from dataclasses import dataclass

from core.orchestra_agents.manifest import AgentManifest


@dataclass(frozen=True)
class RuntimeConfig:
    """Resolved SGR runtime configuration."""

    slug: str
    backend_type: str
    working_dir: str
    system_prompt: str
    host: str
    port: int


def resolve_runtime_config(manifest: AgentManifest | None) -> RuntimeConfig:
    """Build runtime config from manifest and environment."""
    fields: dict[str, str] = (
        {}
        if manifest is None
        else {
            "slug": str(manifest.slug).strip(),
            "backend_type": str(manifest.backend.type).strip(),
            "working_dir": str(manifest.agent.working_dir).strip(),
        }
    )
    return RuntimeConfig(
        slug=_resolve("ORCHESTRA_AGENT_SLUG", fields, "slug", "sgr"),
        backend_type=_resolve(
            "ORCHESTRA_AGENT_BACKEND_TYPE",
            fields,
            "backend_type",
            "sgr_minimax",
        ),
        working_dir=_resolve(
            "ORCHESTRA_AGENT_WORKING_DIR",
            fields,
            "working_dir",
            "/workspace/agents/sgr",
        ),
        system_prompt=manifest.load_system_prompt() if manifest else "",
        host=str(os.getenv("AGENT_HTTP_HOST") or "0.0.0.0").strip() or "0.0.0.0",
        port=int(os.getenv("AGENT_HTTP_PORT", "8787")),
    )


def _resolve(env_key: str, fields: dict[str, str], field: str, default: str) -> str:
    """Resolve a config field from environment or manifest fields."""
    env_value = os.getenv(env_key)
    raw = str(env_value or fields.get(field) or default).strip()
    return raw or default
