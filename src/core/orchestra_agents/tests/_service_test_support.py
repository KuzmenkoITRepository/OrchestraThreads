from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest import mock as umock

from core.orchestra_agents.service.runtime import OrchestraAgentsService


def created_service(root: Path, *, runtime_name: str | None = None) -> Any:
    env: dict[str, str] = {}
    if runtime_name is not None:
        env["ORCHESTRA_AGENTS_RUNTIME"] = runtime_name
    with umock.patch.dict("os.environ", env, clear=False):
        return OrchestraAgentsService.create(manifests_root=str(root))


def resolved_runtime_name(service: Any) -> str:
    manifest = service.state.require_manifest("coding_agent")
    spec = service.state.build_spec(manifest)
    runtime = service.state.resolve_runtime(spec, operation="status")
    return type(runtime).__name__


def research_manifest_yaml() -> str:
    return "\n".join(
        (
            "slug: research_agent",
            "display_name: Research Agent",
            "status: active",
            "agent:",
            "  working_dir: /workspace",
            "  http_endpoint: http://orchestra-agent-research_agent:8787",
            "runtime:",
            "  image: agent-image:latest",
            "backend:",
            "  type: sgr",
        ),
    )
