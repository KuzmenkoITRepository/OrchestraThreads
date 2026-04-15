from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any

from core.orchestra_agents.launch.docker_cli_runtime import DockerCliRuntime
from core.orchestra_agents.tests import docker_driver_test_data as data
from core.orchestra_agents.tests._docker_runtime_test_scenarios import (
    container_exists_command,
    container_running_command,
    inspect_state_command,
)
from core.orchestra_agents.tests._runtime_shell_fakes import (
    MappingShellRunner,
    PrefixCommandCapture,
)

support = import_module("core.orchestra_agents.tests._docker_cli_runtime_case_support")


@dataclass
class DockerRuntimeCase:
    spec: Any
    runtime: DockerCliRuntime
    shell: MappingShellRunner
    run_capture: PrefixCommandCapture | None = None


class DockerRuntimeLifecycleCases:
    @staticmethod
    def start(root: Path) -> DockerRuntimeCase:
        spec = support.characterized_spec(root)
        run_capture = support.run_capture()
        shell = support.start_shell(spec, run_capture)
        return DockerRuntimeCase(
            spec=spec,
            runtime=DockerCliRuntime(shell_runner=shell),
            shell=shell,
            run_capture=run_capture,
        )

    @staticmethod
    def reuse(root: Path) -> DockerRuntimeCase:
        spec = support.characterized_spec(root)
        shell = MappingShellRunner(
            {
                tuple(
                    container_exists_command(spec.container_name)
                ): support.run_capture().result.__class__(
                    0,
                    stdout=f"{spec.container_name}\n",
                ),
                tuple(
                    container_running_command(spec.container_name)
                ): support.run_capture().result.__class__(0, stdout=""),
                (data.DOCKER, "start", spec.container_name): support.run_capture().result.__class__(
                    0, stdout="started\n"
                ),
                tuple(
                    inspect_state_command(spec.container_name)
                ): support.run_capture().result.__class__(
                    0,
                    stdout=import_module("json").dumps(
                        import_module(
                            "core.orchestra_agents.tests._docker_runtime_test_scenarios"
                        ).running_state(health_status="healthy")
                    ),
                ),
            },
        )
        return DockerRuntimeCase(
            spec=spec, runtime=DockerCliRuntime(shell_runner=shell), shell=shell
        )

    @staticmethod
    def stop(root: Path) -> DockerRuntimeCase:
        spec = support.characterized_spec(root)
        shell = MappingShellRunner(
            {
                tuple(
                    container_exists_command(spec.container_name)
                ): support.run_capture().result.__class__(0, stdout=f"{spec.container_name}\n"),
                (data.DOCKER, "stop", spec.container_name): support.run_capture().result.__class__(
                    0, stdout="stopped\n"
                ),
                (
                    data.DOCKER,
                    "rm",
                    "-f",
                    spec.container_name,
                ): support.run_capture().result.__class__(0, stdout="removed\n"),
            },
        )
        return DockerRuntimeCase(
            spec=spec, runtime=DockerCliRuntime(shell_runner=shell), shell=shell
        )

    @staticmethod
    def restart(root: Path) -> DockerRuntimeCase:
        spec = support.characterized_spec(root)
        run_capture = support.run_capture()
        shell = MappingShellRunner(
            {
                tuple(
                    container_exists_command(spec.container_name)
                ): support.run_capture().result.__class__(0, stdout=f"{spec.container_name}\n"),
                (data.DOCKER, "stop", spec.container_name): support.run_capture().result.__class__(
                    0, stdout="stopped\n"
                ),
                (
                    data.DOCKER,
                    "rm",
                    "-f",
                    spec.container_name,
                ): support.run_capture().result.__class__(0, stdout="removed\n"),
                (
                    data.DOCKER,
                    "image",
                    "inspect",
                    spec.image,
                ): support.run_capture().result.__class__(0, stdout="[]"),
                tuple(
                    inspect_state_command(spec.container_name)
                ): support.run_capture().result.__class__(
                    0,
                    stdout=import_module("json").dumps(
                        import_module(
                            "core.orchestra_agents.tests._docker_runtime_test_scenarios"
                        ).running_state(health_status="healthy")
                    ),
                ),
            },
            captures=(run_capture,),
        )
        return DockerRuntimeCase(
            spec=spec,
            runtime=DockerCliRuntime(shell_runner=shell),
            shell=shell,
            run_capture=run_capture,
        )


class DockerRuntimeStatusCases:
    @staticmethod
    def docker_health(root: Path) -> DockerRuntimeCase:
        spec = support.characterized_spec(root)
        shell = MappingShellRunner(
            {
                tuple(
                    inspect_state_command(spec.container_name)
                ): support.run_capture().result.__class__(
                    0,
                    stdout=import_module("json").dumps(
                        import_module(
                            "core.orchestra_agents.tests._docker_runtime_test_scenarios"
                        ).running_state(error="health degraded", health_status="unhealthy")
                    ),
                ),
            },
        )
        return DockerRuntimeCase(
            spec=spec, runtime=DockerCliRuntime(shell_runner=shell), shell=shell
        )

    @staticmethod
    def http_probe(root: Path) -> DockerRuntimeCase:
        spec = support.characterized_spec(root)
        shell = MappingShellRunner(
            {
                tuple(
                    inspect_state_command(spec.container_name)
                ): support.run_capture().result.__class__(
                    0,
                    stdout=import_module("json").dumps(
                        import_module(
                            "core.orchestra_agents.tests._docker_runtime_test_scenarios"
                        ).running_state()
                    ),
                ),
            },
        )
        return DockerRuntimeCase(
            spec=spec, runtime=DockerCliRuntime(shell_runner=shell), shell=shell
        )

    @staticmethod
    def missing_container(root: Path) -> DockerRuntimeCase:
        spec = support.characterized_spec(root)
        shell = MappingShellRunner(
            {
                tuple(
                    inspect_state_command(spec.container_name)
                ): support.run_capture().result.__class__(
                    1, stderr=f"Error: No such container: {spec.container_name}"
                ),
            },
        )
        return DockerRuntimeCase(
            spec=spec, runtime=DockerCliRuntime(shell_runner=shell), shell=shell
        )

    @staticmethod
    def build_image(build_root: Path) -> DockerRuntimeCase:
        dockerfile, spec = support.build_parts(build_root)
        run_capture = support.run_capture()
        shell = support.build_shell(build_root, dockerfile, spec, run_capture)
        runtime = DockerCliRuntime(shell_runner=shell, build_context_root=build_root)
        return DockerRuntimeCase(spec=spec, runtime=runtime, shell=shell, run_capture=run_capture)
