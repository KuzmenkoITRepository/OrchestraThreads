from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import cast

from core.orchestra_agents.tests import docker_driver_test_data as data


def _driver_support_dirname() -> str:
    support = import_module("core.orchestra_agents._docker_driver_support")
    return str(support.COMPOSE_RUNTIME_DIRNAME)


def assert_characterized_compose_start(
    capture: data.ComposeCapture,
    *,
    manifests_root: Path,
) -> None:
    _CharacterizedComposeStart(capture, manifests_root=manifests_root).assert_matches()


def assert_compose_start(capture: data.ComposeCapture) -> None:
    cmd_result, commands, compose_path = capture
    assert cmd_result[data.EXISTS_KEY]
    assert compose_path.exists()
    _assert_compose_service_metadata(compose_path)
    _assert_compose_command_tail(commands[-1], compose_path)


def assert_compose_stop(capture: data.ComposeCapture) -> None:
    cmd_result, commands, compose_path = capture
    assert cmd_result["removed"]
    assert not compose_path.exists()
    assert commands[-1] == [
        data.DOCKER,
        "compose",
        "-p",
        data.COMPOSE_PROJECT,
        "-f",
        str(compose_path),
        "rm",
        "-sf",
        "agent-coding-agent",
    ]


class _CharacterizedComposeStart:
    def __init__(self, capture: data.ComposeCapture, *, manifests_root: Path) -> None:
        cmd_result, commands, compose_path = capture
        self._cmd_result = cmd_result
        self._commands = commands
        self._compose_path = compose_path
        self._manifests_root = manifests_root
        self._service_name = "agent-coding-agent"

    def assert_matches(self) -> None:
        assert self._cmd_result[data.EXISTS_KEY]
        assert (
            self._compose_path
            == self._manifests_root / _driver_support_dirname() / data.COMPOSE_FILE_NAME
        )
        assert self._compose_path.exists()
        assert self._service_payload() == {
            "image": data.AGENT_IMAGE,
            "container_name": data.CODING_AGENT_CONTAINER,
            "restart": "no",
            "working_dir": "/workspace/project",
            "labels": {
                "orchestra.agent_slug": "coding_agent",
                "orchestra.backend_type": "codex_framework",
            },
            "environment": self._environment(),
            "healthcheck": self._healthcheck(),
            "volumes": self._mounts(),
            "command": ["-lc", "python app.py"],
            "entrypoint": "/bin/sh",
        }
        assert self._commands[-1] == [
            data.DOCKER,
            "compose",
            "-p",
            data.COMPOSE_PROJECT,
            "-f",
            str(self._compose_path),
            "up",
            "-d",
            "--no-deps",
            self._service_name,
        ]

    def _service_payload(self) -> dict[str, object]:
        payload = json.loads(self._compose_path.read_text(encoding="utf-8"))
        assert list(payload["services"].keys()) == [self._service_name]
        return cast(dict[str, object], payload["services"][self._service_name])

    def _mounts(self) -> list[str]:
        return [
            f"{self._manifests_root}:/orchestra/agents:ro",
            f"{self._manifests_root / 'coding_agent'}:/workspace/project:rw",
            (
                f"{self._manifests_root / 'coding_agent' / 'logs' / 'coding_agent'}:"
                f"/var/log/{data.CODING_AGENT_CONTAINER}:ro"
            ),
        ]

    def _environment(self) -> dict[str, str]:
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

    def _healthcheck(self) -> dict[str, object]:
        return {
            "test": [
                "CMD-SHELL",
                (
                    'python -c "import sys,urllib.request; '
                    "sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8787/healthz').status == 200 else 1)\""
                ),
            ],
            "interval": "30s",
            "timeout": "5s",
            "start_period": "10s",
            "retries": 3,
        }


def _assert_compose_service_metadata(compose_path: Path) -> None:
    service = json.loads(compose_path.read_text(encoding="utf-8"))["services"]["agent-coding-agent"]
    assert service["container_name"] == data.CODING_AGENT_CONTAINER
    assert service["labels"]["orchestra.agent_slug"] == "coding_agent"
    assert service["environment"]["ORCHESTRA_AGENT_MANIFESTS_DIR"] == "/orchestra/agents"


def _assert_compose_command_tail(command: data.DockerCommand, compose_path: Path) -> None:
    assert command == [
        data.DOCKER,
        "compose",
        "-p",
        data.COMPOSE_PROJECT,
        "-f",
        str(compose_path),
        "up",
        "-d",
        "--no-deps",
        "agent-coding-agent",
    ]
