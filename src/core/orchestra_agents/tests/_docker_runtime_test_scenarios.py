from __future__ import annotations

from typing import Any

from core.orchestra_agents.tests import docker_driver_test_data as data


def container_exists_command(container_name: str) -> list[str]:
    return [
        data.DOCKER,
        "ps",
        "-a",
        "--filter",
        f"name=^{container_name}$",
        "--format",
        "{{.Names}}",
    ]


def container_running_command(container_name: str) -> list[str]:
    return [
        data.DOCKER,
        "ps",
        "--filter",
        f"name=^{container_name}$",
        "--format",
        "{{.Names}}",
    ]


def inspect_state_command(container_name: str) -> list[str]:
    return [data.DOCKER, "inspect", container_name, "--format", "{{json .State}}"]


def running_state(*, error: str = "", health_status: str | None = None) -> dict[str, Any]:
    state: dict[str, Any] = {
        "Running": True,
        "Status": data.RUNNING_KEY,
        "StartedAt": "2025-01-01T00:00:00Z",
        "Error": error,
    }
    if health_status is not None:
        state["Health"] = {"Status": health_status}
    return state
