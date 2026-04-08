from __future__ import annotations

import json
from pathlib import Path

from core.orchestra_agents.tests import docker_driver_test_data as data


def _docker_prefix(command: data.DockerCommand, size: int) -> data.DockerCommand:
    return command[:size]


def assert_restart_commands(commands: data.DockerCommands) -> None:
    assert _docker_prefix(commands[0], 2) == [data.DOCKER, "stop"]
    assert commands[0][2] == data.CODING_AGENT_CONTAINER
    assert _docker_prefix(commands[1], 4) == [
        data.DOCKER,
        "rm",
        "-f",
        data.CODING_AGENT_CONTAINER,
    ]
    assert _docker_prefix(commands[-1], 3) == [
        data.DOCKER,
        data.RUN_COMMAND,
        data.DETACHED_FLAG,
    ]


def assert_build_cmds(
    commands: data.DockerCommands,
    root: Path,
    dockerfile_name: str,
) -> None:
    assert _docker_prefix(commands[0], 3) == [data.DOCKER, "image", "inspect"]
    assert _docker_prefix(commands[1], 2) == [data.DOCKER, "build"]
    assert str(root / dockerfile_name) in commands[1]
    assert _docker_prefix(commands[2], 3) == [
        data.DOCKER,
        data.RUN_COMMAND,
        data.DETACHED_FLAG,
    ]


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
