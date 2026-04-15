from __future__ import annotations

from pathlib import Path

from core.orchestra_agents.tests import _docker_run_assertion_support as support
from core.orchestra_agents.tests import docker_driver_test_data as data


def assert_restart_commands(commands: data.DockerCommands) -> None:
    assert commands[0][:2] == [data.DOCKER, "stop"]
    assert commands[0][2] == data.CODING_AGENT_CONTAINER
    assert commands[1][:4] == [
        data.DOCKER,
        "rm",
        "-f",
        data.CODING_AGENT_CONTAINER,
    ]
    assert commands[-1][:3] == [
        data.DOCKER,
        data.RUN_COMMAND,
        data.DETACHED_FLAG,
    ]


def assert_build_cmds(
    commands: data.DockerCommands,
    root: Path,
    dockerfile_name: str,
) -> None:
    assert commands[0][:3] == [data.DOCKER, "image", "inspect"]
    assert commands[1][:2] == [data.DOCKER, "build"]
    assert str(root / dockerfile_name) in commands[1]
    assert commands[2][:3] == [
        data.DOCKER,
        data.RUN_COMMAND,
        data.DETACHED_FLAG,
    ]


def assert_runtime_resolution(
    command: data.DockerCommand,
    *,
    image: str,
    module: str,
    pythonpath: str,
) -> None:
    assert image in command
    assert module in command
    assert f"PYTHONPATH={pythonpath}" in command


def assert_characterized_run_command(
    command: data.DockerCommand,
    *,
    manifests_root: Path,
) -> None:
    _CharacterizedRunCommand(command, manifests_root=manifests_root).assert_matches()


class _CharacterizedRunCommand:
    def __init__(self, command: data.DockerCommand, *, manifests_root: Path) -> None:
        self._command = command
        self._manifests_root = manifests_root

    def assert_matches(self) -> None:
        assert self._command[:3] == [data.DOCKER, data.RUN_COMMAND, data.DETACHED_FLAG]
        assert self._command[-3:] == [data.AGENT_IMAGE, "-lc", "python app.py"]
        self._assert_metadata()
        self._assert_health()
        self._assert_mounts()
        self._assert_environment()

    def _assert_metadata(self) -> None:
        assert support.metadata_snapshot(self._command) == {
            "--name": [data.CODING_AGENT_CONTAINER],
            "--restart": ["no"],
            "--label": [
                "orchestra.agent_slug=coding_agent",
                "orchestra.backend_type=codex_framework",
            ],
            "--workdir": ["/workspace/project"],
            "--network": ["agents-net"],
            "--entrypoint": ["/bin/sh"],
        }

    def _assert_health(self) -> None:
        assert support.flag_values(self._command, "--health-cmd") == [support.health_command()]
        assert support.flag_values(self._command, "--health-interval") == ["30s"]
        assert support.flag_values(self._command, "--health-timeout") == ["5s"]
        assert support.flag_values(self._command, "--health-start-period") == ["10s"]
        assert support.flag_values(self._command, "--health-retries") == ["3"]

    def _assert_mounts(self) -> None:
        assert support.flag_values(self._command, "-v") == support.expected_mounts(
            self._manifests_root
        )

    def _assert_environment(self) -> None:
        assert support.environment_entries(self._command) == support.expected_environment()
