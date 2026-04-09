from __future__ import annotations

from pathlib import Path
from typing import Any

from core.orchestra_agents.docker_driver import DockerDriver
from core.orchestra_agents.tests import _docker_driver_test_constants as const


def compose_driver(root: Path) -> DockerDriver:
    return DockerDriver(
        manifests_root=root,
        compose_project_name=const.COMPOSE_PROJECT,
        compose_runtime_dir=root / "compose-runtime",
    )


def compose_file(root: Path) -> Path:
    return root / "compose-runtime" / const.COMPOSE_FILE_NAME


def compose_status_payload() -> dict[str, Any]:
    return {
        const.EXISTS_KEY: True,
        const.RUNNING_KEY: True,
        const.HEALTHY_KEY: True,
    }


def missing_build_status() -> dict[str, Any]:
    return {
        const.EXISTS_KEY: True,
        const.RUNNING_KEY: True,
        const.HEALTHY_KEY: False,
    }


def compose_labels() -> dict[str, str]:
    return {
        "com.docker.compose.project": const.COMPOSE_PROJECT,
        "com.docker.compose.service": "agent-coding-agent",
    }
