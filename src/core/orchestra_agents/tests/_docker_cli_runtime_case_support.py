from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest import mock as umock

from core.orchestra_agents.launch._runtime_shell import ShellResult
from core.orchestra_agents.tests import docker_driver_test_data as data
from core.orchestra_agents.tests._docker_runtime_test_scenarios import (
    container_exists_command,
    inspect_state_command,
    running_state,
)
from core.orchestra_agents.tests._runtime_shell_fakes import (
    MappingShellRunner,
    PrefixCommandCapture,
)
from core.orchestra_agents.tests._runtime_test_spec_builders import (
    build_characterized_spec,
    build_unified_spec,
)


def characterized_spec(root: Path) -> Any:
    with umock.patch.dict("os.environ", {data.OPENAI_API_KEY: "secret"}, clear=False):
        return build_characterized_spec(root, default_network="agents-net")


def run_capture() -> PrefixCommandCapture:
    return PrefixCommandCapture(
        prefix=(data.DOCKER, data.RUN_COMMAND, data.DETACHED_FLAG),
        result=ShellResult(0, stdout="container-id\n"),
    )


def start_shell(spec: Any, capture: PrefixCommandCapture) -> MappingShellRunner:
    return MappingShellRunner(
        {
            tuple(container_exists_command(spec.container_name)): ShellResult(0, stdout=""),
            (data.DOCKER, "image", "inspect", spec.image): ShellResult(0, stdout="[]"),
            tuple(inspect_state_command(spec.container_name)): ShellResult(
                0, stdout=json.dumps(running_state(health_status="healthy"))
            ),
        },
        captures=(capture,),
    )


def build_parts(build_root: Path) -> tuple[Path, Any]:
    dockerfile = build_root / "docker" / "backends" / "agent_mux" / "Dockerfile"
    dockerfile.parent.mkdir(parents=True, exist_ok=True)
    dockerfile.write_text("FROM scratch\n", encoding="utf-8")
    manifests_root = build_root / "agents"
    manifests_root.mkdir()
    return dockerfile, build_unified_spec(manifests_root, backend_type="agent_mux")


def build_shell(
    build_root: Path,
    dockerfile: Path,
    spec: Any,
    capture: PrefixCommandCapture,
) -> MappingShellRunner:
    build_target = str(build_root.resolve())
    return MappingShellRunner(
        {
            tuple(container_exists_command(spec.container_name)): ShellResult(0, stdout=""),
            (data.DOCKER, "image", "inspect", spec.image): ShellResult(1, stderr="image not found"),
            (
                data.DOCKER,
                "build",
                "-f",
                str(dockerfile.resolve()),
                "-t",
                spec.image,
                build_target,
            ): ShellResult(0, stdout="built\n"),
            tuple(inspect_state_command(spec.container_name)): ShellResult(
                0, stdout=json.dumps(running_state(health_status="healthy"))
            ),
        },
        captures=(capture,),
    )
