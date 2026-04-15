from __future__ import annotations

from pathlib import Path
from typing import Protocol

from core.orchestra_agents.tests import docker_driver_test_data as data
from core.orchestra_agents.tests._runtime_shell_fakes import QueueShellRunner


class ComposeCaseLike(Protocol):
    compose_path: Path
    shell: QueueShellRunner


def compose_capture(case: ComposeCaseLike) -> data.ComposeCapture:
    return ({data.EXISTS_KEY: True}, start_commands(case), case.compose_path)


def compose_stop_capture(case: ComposeCaseLike, removed: bool) -> data.ComposeCapture:
    return ({"removed": removed}, shell_commands(case), case.compose_path)


def build_dockerfile_arg(shell: QueueShellRunner) -> str:
    return str(shell.calls[1][0][3])


def shell_commands(case: ComposeCaseLike) -> list[list[str]]:
    return [command for command, _ in case.shell.calls]


def start_commands(case: ComposeCaseLike) -> list[list[str]]:
    return shell_commands(case)[:-1]
