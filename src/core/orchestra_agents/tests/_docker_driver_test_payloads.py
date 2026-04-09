from __future__ import annotations

from pathlib import Path
from typing import Any

from core.orchestra_agents.manifest import AgentManifest
from core.orchestra_agents.tests import _docker_driver_test_constants as const


def manifest_payload() -> dict[str, Any]:
    return {
        "slug": "coding_agent",
        "display_name": "Coding Agent",
        const.STATUS_KEY: "active",
        "agent": {
            "working_dir": "/workspace",
            "http_endpoint": "http://{container_name}:8787",
            "system_prompt_file": "system_prompt.md",
        },
        "runtime": {
            const.DRIVER_KEY: const.DOCKER,
            const.IMAGE_KEY: const.AGENT_IMAGE,
            "command": ["python", "-m", "core.orchestra_agents.backends.example.main"],
            "mounts": [
                {
                    "type": "bind",
                    "source": ".",
                    "target": "/workspace",
                    "mode": "rw",
                },
            ],
            "env": {"LOG_LEVEL": "INFO"},
            "env_passthrough": [const.OPENAI_API_KEY],
        },
        "backend": {"type": "codex_framework"},
    }


def create_manifest(
    manifests_root: Path,
    *,
    image: str = const.AGENT_IMAGE,
    with_system_prompt: bool = False,
) -> AgentManifest:
    agent_dir = manifests_root / "coding_agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = agent_dir / "manifest.yaml"
    manifest_path.write_text("{}", encoding="utf-8")
    if with_system_prompt:
        (agent_dir / "system_prompt.md").write_text("prompt", encoding="utf-8")
    payload = manifest_payload()
    payload["runtime"][const.IMAGE_KEY] = image
    return AgentManifest.from_dict(payload, manifest_path=manifest_path)


def unified_manifest_payload(*, backend_type: str) -> dict[str, Any]:
    return {
        "slug": "coding_agent",
        "display_name": "Coding Agent",
        const.STATUS_KEY: "active",
        "agent": {
            "working_dir": "/workspace/agents/coding_agent",
            "http_endpoint": "http://{container_name}:8787",
            "system_prompt_file": "system_prompt.md",
        },
        "runtime": {
            const.DRIVER_KEY: const.DOCKER,
            "mounts": [
                {
                    "type": "bind",
                    "source": ".",
                    "target": "/workspace",
                    "mode": "rw",
                },
            ],
            "env": {"LOG_LEVEL": "INFO"},
        },
        "backend": {"type": backend_type, "config": unified_backend_config(backend_type)},
    }


def unified_backend_config(backend_type: str) -> dict[str, Any]:
    if backend_type == "sgr_minimax":
        return {"route_policy": "codex_only", "model": "cx/gpt-5.4-mini"}
    if backend_type == "agent_mux":
        return {
            "role": "worker",
            "llm_route_policy": "minimax_only",
            "model": "MiniMax-M2.7",
        }
    if backend_type == "opencode_omo":
        return {"model": "cx/gpt-5.4-mini"}
    return {}


def create_unified_manifest(
    manifests_root: Path,
    *,
    backend_type: str,
) -> AgentManifest:
    agent_dir = manifests_root / "coding_agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = agent_dir / "manifest.yaml"
    manifest_path.write_text("{}", encoding="utf-8")
    (agent_dir / "system_prompt.md").write_text("prompt", encoding="utf-8")
    payload = unified_manifest_payload(backend_type=backend_type)
    return AgentManifest.from_dict(payload, manifest_path=manifest_path)
