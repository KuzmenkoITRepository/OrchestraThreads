from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.orchestra_agents.launch.launch_spec import LaunchSpec
from core.orchestra_agents.tests import docker_driver_test_data as data


def assert_characterized_launch_spec(spec: LaunchSpec, *, manifests_root: Path) -> None:
    _LaunchSpecCoreAssertions(spec, manifests_root).assert_matches()
    _LaunchSpecHealthAssertions(spec, manifests_root).assert_matches()


@dataclass(frozen=True)
class _LaunchSpecCoreAssertions:
    _spec: LaunchSpec
    _manifests_root: Path

    def assert_matches(self) -> None:
        self._assert_identity()
        self._assert_runtime()
        self._assert_env_and_mounts()

    def _assert_identity(self) -> None:
        assert self._spec.container_name == data.CODING_AGENT_CONTAINER
        assert self._spec.image == data.AGENT_IMAGE
        assert self._spec.labels == (
            ("orchestra.agent_slug", "coding_agent"),
            ("orchestra.backend_type", "codex_framework"),
        )

    def _assert_runtime(self) -> None:
        assert self._spec.command == ("-lc", "python app.py")
        assert self._spec.entrypoint == "/bin/sh"
        assert self._spec.working_dir == "/workspace/project"
        assert self._spec.default_network == "agents-net"

    def _assert_env_and_mounts(self) -> None:
        mounts = tuple(
            (mount.type, mount.source, mount.target, mount.mode) for mount in self._spec.mounts
        )
        assert mounts == _expected_mounts(self._manifests_root)
        assert dict(self._spec.env) == _expected_env_map()


@dataclass(frozen=True)
class _LaunchSpecHealthAssertions:
    _spec: LaunchSpec
    _manifests_root: Path

    def assert_matches(self) -> None:
        self._assert_health()
        self._assert_compose()

    def _assert_health(self) -> None:
        health = {
            "test": self._spec.healthcheck.test,
            "interval": self._spec.healthcheck.interval,
            "timeout": self._spec.healthcheck.timeout,
            "start_period": self._spec.healthcheck.start_period,
            "retries": self._spec.healthcheck.retries,
        }
        assert health == {
            "test": _expected_health_test(),
            "interval": "30s",
            "timeout": "5s",
            "start_period": "10s",
            "retries": 3,
        }

    def _assert_compose(self) -> None:
        compose = {
            "compose_file_path": self._spec.compose_file_path,
            "compose_service_name": self._spec.compose_service_name,
        }
        assert compose == {
            "compose_file_path": _expected_compose_path(self._manifests_root),
            "compose_service_name": "agent-coding-agent",
        }


def _expected_env_map() -> dict[str, str]:
    return {
        "ORCHESTRA_AGENT_SLUG": "coding_agent",
        "ORCHESTRA_AGENT_BACKEND_TYPE": "codex_framework",
        "ORCHESTRA_AGENT_HTTP_ENDPOINT": f"http://{data.CODING_AGENT_CONTAINER}:8787",
        "ORCHESTRA_AGENT_WORKING_DIR": "/workspace/project",
        "ORCHESTRA_AGENT_ALLOWED_PEER_AGENT_SLUGS": "",
        "ORCHESTRA_AGENT_MANIFESTS_DIR": "/orchestra/agents",
        "ORCHESTRA_AGENT_MANIFEST": "/orchestra/agents/coding_agent/manifest.yaml",
        "ORCHESTRA_AGENT_SYSTEM_PROMPT_FILE": "system_prompt.md",
        "LOG_LEVEL": "DEBUG",
        "RUNTIME_TAG": (
            "coding_agent:orchestra-agent-coding_agent:codex_framework:/workspace/project"
        ),
        data.OPENAI_API_KEY: "secret",
    }


def _expected_mounts(manifests_root: Path) -> tuple[tuple[str, str, str, str], ...]:
    return (
        ("bind", str(manifests_root), "/orchestra/agents", "ro"),
        ("bind", str(manifests_root / "coding_agent"), "/workspace/project", "rw"),
        (
            "bind",
            str(manifests_root / "coding_agent" / "logs" / "coding_agent"),
            f"/var/log/{data.CODING_AGENT_CONTAINER}",
            "ro",
        ),
    )


def _expected_health_test() -> tuple[str, str]:
    return (
        "CMD-SHELL",
        'python -c "import sys,urllib.request; '
        "sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8787/healthz').status == 200 else 1)\"",
    )


def _expected_compose_path(manifests_root: Path) -> Path:
    return manifests_root / "compose-runtime" / data.COMPOSE_FILE_NAME
