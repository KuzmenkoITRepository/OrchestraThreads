from __future__ import annotations

from dataclasses import FrozenInstanceError
from importlib import import_module
from pathlib import Path
from typing import Any, Protocol
from unittest import TestCase

launch_spec_module = import_module("core.orchestra_agents.launch.launch_spec")
runtime_protocol_module = import_module("core.orchestra_agents.launch.runtime_protocol")


class _LaunchSpecLike(Protocol):
    slug: str
    container_name: str


class _DummyRuntime:
    def container_name(self, spec: _LaunchSpecLike) -> str:
        return spec.container_name

    def start(self, spec: _LaunchSpecLike) -> Any:
        return launch_spec_module.RuntimeActionResult(
            action="start",
            container_name=spec.container_name,
            success=True,
        )

    def stop(self, spec: _LaunchSpecLike, *, remove: bool = False) -> Any:
        return launch_spec_module.RuntimeActionResult(
            action="stop",
            container_name=spec.container_name,
            success=True,
            removed=remove,
        )

    def restart(self, spec: _LaunchSpecLike) -> Any:
        return launch_spec_module.RuntimeActionResult(
            action="restart",
            container_name=spec.container_name,
            success=True,
        )

    def status(self, spec: _LaunchSpecLike) -> Any:
        return launch_spec_module.RuntimeStatusPayload(
            slug=spec.slug,
            container_name=spec.container_name,
            exists=True,
            running=True,
            healthy=True,
        )


def _launch_spec() -> Any:
    return launch_spec_module.LaunchSpec(
        slug="coding_agent",
        container_name="orchestra-agent-coding_agent",
        image="example/runtime:latest",
        labels=(("orchestra.agent_slug", "coding_agent"), ("orchestra.backend_type", "codex")),
        env=(("ORCHESTRA_AGENT_SLUG", "coding_agent"), ("LOG_LEVEL", "INFO")),
        mounts=(
            launch_spec_module.ResolvedMount(
                type="bind", source=".", target="/workspace", mode="rw"
            ),
        ),
        command=("python", "-m", "core.orchestra_agents.backends.example.main"),
        entrypoint="/bin/sh",
        working_dir="/workspace",
        default_network="agents-net",
        healthcheck=launch_spec_module.ResolvedHealthcheck(
            test=("CMD-SHELL", "curl -fsS http://127.0.0.1:8787/healthz"),
        ),
        compose_file_path=Path("/tmp/agents/coding_agent.yaml"),
        compose_service_name="agent-coding_agent",
    )


def _expected_launch_spec_payload() -> dict[str, object]:
    return {
        "slug": "coding_agent",
        "container_name": "orchestra-agent-coding_agent",
        "image": "example/runtime:latest",
        "labels": {
            "orchestra.agent_slug": "coding_agent",
            "orchestra.backend_type": "codex",
        },
        "env": {
            "ORCHESTRA_AGENT_SLUG": "coding_agent",
            "LOG_LEVEL": "INFO",
        },
        "mounts": [
            {
                "type": "bind",
                "source": ".",
                "target": "/workspace",
                "mode": "rw",
            },
        ],
        "command": [
            "python",
            "-m",
            "core.orchestra_agents.backends.example.main",
        ],
        "entrypoint": "/bin/sh",
        "working_dir": "/workspace",
        "default_network": "agents-net",
        "healthcheck": {
            "test": ["CMD-SHELL", "curl -fsS http://127.0.0.1:8787/healthz"],
            "interval": "30s",
            "timeout": "5s",
            "start_period": "10s",
            "retries": 3,
        },
        "compose_file_path": "/tmp/agents/coding_agent.yaml",
        "compose_service_name": "agent-coding_agent",
    }


class LaunchSpecTests(TestCase):
    def test_launch_spec_is_frozen(self) -> None:
        spec = _launch_spec()

        with self.assertRaises(FrozenInstanceError):
            spec.container_name = "other"

    def test_launch_spec_serializes_nested_contracts(self) -> None:
        payload = _launch_spec().to_dict()

        self.assertEqual(payload, _expected_launch_spec_payload())

    def test_healthcheck_defaults_match_parity(self) -> None:
        healthcheck = launch_spec_module.ResolvedHealthcheck()

        self.assertEqual(healthcheck.interval, "30s")
        self.assertEqual(healthcheck.timeout, "5s")
        self.assertEqual(healthcheck.start_period, "10s")
        self.assertEqual(healthcheck.retries, 3)


class RuntimeProtocolTests(TestCase):
    def test_runtime_payloads_are_dict_serializable(self) -> None:
        status = launch_spec_module.RuntimeStatusPayload(
            slug="coding_agent",
            container_name="orchestra-agent-coding_agent",
            exists=True,
            running=True,
            healthy=False,
            backend_type="codex_framework",
            http_endpoint="http://orchestra-agent-coding_agent:8787",
            docker_status="running",
            health_status={
                "ok": False,
                "status_code": None,
                "source": "docker",
                "status": "unhealthy",
            },
            started_at="2025-01-01T00:00:00Z",
            last_error="health degraded",
        )
        action = launch_spec_module.RuntimeActionResult(
            action="start",
            container_name="orchestra-agent-coding_agent",
            success=True,
            message="started",
            status=status,
        )

        self.assertEqual(status.to_dict()["container_name"], "orchestra-agent-coding_agent")
        self.assertEqual(action.to_dict()["status"], status.to_dict())

    def test_container_runtime_protocol_is_structural(self) -> None:
        self.assertIsInstance(_DummyRuntime(), runtime_protocol_module.ContainerRuntime)
