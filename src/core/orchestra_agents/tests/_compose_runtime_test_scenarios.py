from __future__ import annotations

import json
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError

from core.orchestra_agents.launch._runtime_shell import ShellResult
from core.orchestra_agents.launch.launch_spec import (
    LaunchSpec,
    ResolvedHealthcheck,
    ResolvedMount,
)
from core.orchestra_agents.tests import docker_driver_test_data as data


def status_spec() -> LaunchSpec:
    return LaunchSpec(
        slug="coding_agent",
        container_name=data.CODING_AGENT_CONTAINER,
        image=data.AGENT_IMAGE,
        env=(
            ("ORCHESTRA_AGENT_BACKEND_TYPE", "codex_framework"),
            ("ORCHESTRA_AGENT_HTTP_ENDPOINT", f"http://{data.CODING_AGENT_CONTAINER}:8787"),
        ),
        mounts=(ResolvedMount(type="bind", source="/tmp", target="/tmp", mode="rw"),),
        command=("python",),
        healthcheck=ResolvedHealthcheck(test=("CMD-SHELL", "true")),
        compose_file_path=Path("/tmp/spec.yaml"),
        compose_service_name="agent-coding-agent",
    )


def missing_container_spec() -> LaunchSpec:
    return LaunchSpec(
        slug="coding_agent",
        container_name=data.CODING_AGENT_CONTAINER,
        image=data.AGENT_IMAGE,
        compose_file_path=Path("/tmp/spec.yaml"),
        compose_service_name="agent-coding-agent",
    )


def healthy_state_result() -> ShellResult:
    return ShellResult(0, stdout=_state_payload(error="", health_status="healthy"))


def running_state_result() -> ShellResult:
    return ShellResult(0, stdout=_state_payload(error="", health_status=None))


def unhealthy_state_result() -> ShellResult:
    return ShellResult(
        0,
        stdout=_state_payload(error="health degraded", health_status="unhealthy"),
    )


def http_error() -> HTTPError:
    return HTTPError(
        "http://127.0.0.1:8787/healthz",
        500,
        "boom",
        hdrs=Message(),
        fp=None,
    )


def _state_payload(*, error: str, health_status: str | None) -> str:
    payload = {
        "Running": True,
        "Status": "running",
        "StartedAt": "2025-01-01T00:00:00Z",
        "Error": error,
    }
    if health_status is not None:
        payload["Health"] = {"Status": health_status}
    return json.dumps(payload)
