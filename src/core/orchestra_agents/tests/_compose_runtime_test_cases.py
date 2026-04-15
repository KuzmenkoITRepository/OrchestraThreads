from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest import mock as umock

from core.orchestra_agents.launch._runtime_shell import ShellResult
from core.orchestra_agents.launch.compose_runtime import ComposeRuntime
from core.orchestra_agents.launch.launch_spec import LaunchSpec
from core.orchestra_agents.tests import docker_driver_test_data as data
from core.orchestra_agents.tests._compose_runtime_test_scenarios import healthy_state_result
from core.orchestra_agents.tests._runtime_shell_fakes import QueueShellRunner
from core.orchestra_agents.tests._runtime_test_spec_builders import (
    build_characterized_spec,
    build_spec,
    driver_support_dirname,
)


@dataclass
class ComposeCase:
    root: Path
    spec: LaunchSpec
    runtime: ComposeRuntime
    shell: QueueShellRunner

    @property
    def compose_path(self) -> Path:
        return self.root / driver_support_dirname() / data.COMPOSE_FILE_NAME


class ComposeCaseFactory:
    @staticmethod
    def characterized_start(root: Path) -> ComposeCase:
        shell = queue_shell(
            ShellResult(0, stdout="[]"),
            ShellResult(0, stdout=""),
            ShellResult(0, stdout=""),
            healthy_state_result(),
        )
        with umock.patch.dict("os.environ", {data.OPENAI_API_KEY: "secret"}, clear=False):
            spec = build_characterized_spec(root)
        return ComposeCase(root=root, spec=spec, runtime=_runtime(root, shell), shell=shell)

    @staticmethod
    def legacy_replace(root: Path) -> ComposeCase:
        return _compose_case(
            root,
            queue_shell(
                ShellResult(0, stdout="[]"),
                ShellResult(0, stdout=f"{data.CODING_AGENT_CONTAINER}\n"),
                ShellResult(0, stdout="{}"),
                ShellResult(0, stdout="removed\n"),
                ShellResult(0, stdout="compose-ok\n"),
                healthy_state_result(),
            ),
        )

    @staticmethod
    def missing_image(root: Path) -> tuple[ComposeCase, Path]:
        dockerfile = _compose_dockerfile(root)
        case = _compose_case(
            root,
            queue_shell(
                ShellResult(1, stderr="image missing\n"),
                ShellResult(0, stdout="built\n"),
                ShellResult(0, stdout=""),
                ShellResult(0, stdout="compose-ok\n"),
                healthy_state_result(),
            ),
            image=data.MUX_RUNTIME_IMAGE,
        )
        return case, dockerfile

    @staticmethod
    def restart(root: Path) -> ComposeCase:
        return _compose_case(
            root,
            queue_shell(
                ShellResult(0, stdout="[]"),
                ShellResult(0, stdout=""),
                ShellResult(0, stdout=""),
                healthy_state_result(),
            ),
        )

    @staticmethod
    def stop(root: Path) -> ComposeCase:
        case = _compose_case(
            root,
            queue_shell(
                ShellResult(0, stdout=f"{data.CODING_AGENT_CONTAINER}\n"),
                ShellResult(0, stdout="removed\n"),
            ),
        )
        compose_path = Path(case.spec.compose_file_path or "")
        compose_path.parent.mkdir(parents=True, exist_ok=True)
        compose_path.write_text("{}", encoding="utf-8")
        return case

    @staticmethod
    def missing_metadata(root: Path) -> ComposeCase:
        return _compose_case(
            root,
            queue_shell(ShellResult(0, stdout=f"{data.CODING_AGENT_CONTAINER}\n")),
        )


def queue_shell(*results: ShellResult) -> QueueShellRunner:
    shell = QueueShellRunner()
    shell.push_many(*results)
    return shell


def _compose_case(root: Path, shell: QueueShellRunner, *, image: str | None = None) -> ComposeCase:
    kwargs = {} if image is None else {"image": image}
    spec = build_spec(root, factory_kwargs=kwargs)
    return ComposeCase(root=root, spec=spec, runtime=_runtime(root, shell), shell=shell)


def _runtime(root: Path, shell: QueueShellRunner) -> ComposeRuntime:
    return ComposeRuntime(
        compose_project_name=data.COMPOSE_PROJECT,
        shell_runner=shell,
        build_context_root=root,
    )


def _compose_dockerfile(root: Path) -> Path:
    dockerfile = root / "docker" / "backends" / "agent_mux" / "Dockerfile"
    dockerfile.parent.mkdir(parents=True, exist_ok=True)
    dockerfile.write_text("FROM scratch\n", encoding="utf-8")
    return dockerfile
