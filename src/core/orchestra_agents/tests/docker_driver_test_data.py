from __future__ import annotations

from pathlib import Path
from typing import Any

from core.orchestra_agents.docker_driver import DockerDriver
from core.orchestra_agents.manifest import AgentManifest

DockerCommand = list[str]
DockerCommands = list[DockerCommand]
BuildCapture = tuple[dict[str, Any], DockerCommands, Path]
ComposeCapture = tuple[dict[str, Any], DockerCommands, Path]

DRIVER_KEY = "driver"
IMAGE_KEY = "image"
DOCKER = "docker"
RUN_COMMAND = "run"
DETACHED_FLAG = "-d"
OPENAI_API_KEY = "OPENAI_API_KEY"
RUN_PATH = "core.orchestra_agents.docker_driver._run"
CODING_AGENT_CONTAINER = "orchestra-agent-coding_agent"
EXISTS_KEY = "exists"
HEALTHY_KEY = "healthy"
STATUS_KEY = "status"
RUNNING_KEY = "running"
AGENT_IMAGE = "agent-image:latest"
MUX_RUNTIME_IMAGE = "orchestra-agent-mux-runtime:latest"
OPENCODE_RUNTIME_IMAGE = "orchestra-opencode-runtime:latest"
COMPOSE_PROJECT = "orchestrathreads-test"
COMPOSE_ENV_KEY = "ORCHESTRA_AGENTS_COMPOSE_PROJECT_NAME"
COMPOSE_FILE_NAME = "coding_agent.yaml"


def manifest_payload() -> dict[str, Any]:
    return {
        "slug": "coding_agent",
        "display_name": "Coding Agent",
        STATUS_KEY: "active",
        "agent": {
            "working_dir": "/workspace",
            "http_endpoint": "http://{container_name}:8787",
            "system_prompt_file": "system_prompt.md",
        },
        "runtime": {
            DRIVER_KEY: DOCKER,
            IMAGE_KEY: AGENT_IMAGE,
            "command": ["python", "-m", "agent_runtime.main"],
            "mounts": [
                {
                    "type": "bind",
                    "source": ".",
                    "target": "/workspace",
                    "mode": "rw",
                },
            ],
            "env": {"LOG_LEVEL": "INFO"},
            "env_passthrough": [OPENAI_API_KEY],
        },
        "backend": {"type": "codex_framework"},
    }


def create_manifest(
    manifests_root: Path,
    *,
    image: str = "agent-image:latest",
    with_system_prompt: bool = False,
) -> AgentManifest:
    agent_dir = manifests_root / "coding_agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = agent_dir / "manifest.yaml"
    manifest_path.write_text("{}", encoding="utf-8")
    if with_system_prompt:
        (agent_dir / "system_prompt.md").write_text("prompt", encoding="utf-8")
    payload = manifest_payload()
    payload["runtime"][IMAGE_KEY] = image
    return AgentManifest.from_dict(payload, manifest_path=manifest_path)


def compose_driver(root: Path) -> DockerDriver:
    return DockerDriver(
        manifests_root=root,
        compose_project_name=COMPOSE_PROJECT,
        compose_runtime_dir=root / "compose-runtime",
    )


def compose_file(root: Path) -> Path:
    return root / "compose-runtime" / COMPOSE_FILE_NAME


def compose_status_payload() -> dict[str, Any]:
    return {EXISTS_KEY: True, RUNNING_KEY: True, HEALTHY_KEY: True}


def missing_build_status() -> dict[str, Any]:
    return {EXISTS_KEY: True, RUNNING_KEY: True, HEALTHY_KEY: False}


def compose_labels() -> dict[str, str]:
    return {
        "com.docker.compose.project": COMPOSE_PROJECT,
        "com.docker.compose.service": "agent-coding-agent",
    }
