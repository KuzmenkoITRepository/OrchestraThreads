"""Helper collaborators for Docker CLI runtime orchestration."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from urllib import error as urlerror
from urllib import request as urlrequest

from core.orchestra_agents.launch import backend_profiles
from core.orchestra_agents.launch._runtime_shell import (
    ShellCommandRunner,
    ShellResult,
    checked_command,
)
from core.orchestra_agents.launch._runtime_status import RuntimeStatusSupport
from core.orchestra_agents.launch.launch_spec import (
    LaunchSpec,
    RuntimeActionResult,
    RuntimeStatusPayload,
)

_HTTP_OK = 200


@dataclass(frozen=True)
class DockerTransportSupport:
    shell_runner: ShellCommandRunner
    status_support: RuntimeStatusSupport

    def container_exists(self, container_name: str) -> bool:
        """Check whether named container exists in Docker."""

        result = self.shell_runner(
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                f"name=^{container_name}$",
                "--format",
                "{{.Names}}",
            ],
            timeout=30,
        )
        if result.returncode != 0:
            return False
        names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return container_name in names

    def container_running(self, container_name: str) -> bool:
        """Check whether named container is currently running."""

        result = self.shell_runner(
            ["docker", "ps", "--filter", f"name=^{container_name}$", "--format", "{{.Names}}"],
            timeout=30,
        )
        if result.returncode != 0:
            return False
        names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return container_name in names

    def stop_container(self, spec: LaunchSpec, *, remove: bool) -> RuntimeActionResult:
        """Stop existing container, optionally removing it."""

        checked_command(
            self.shell_runner,
            ["docker", "stop", spec.container_name],
            timeout=120,
            error_message=f"failed to stop {spec.container_name}",
        )
        removed = self._remove_container(spec.container_name, remove=remove)
        return RuntimeActionResult(
            action="stop",
            container_name=spec.container_name,
            success=True,
            removed=removed,
            status=self.status_support.stopped_status(spec, removed=removed),
        )

    def inspect_status(
        self,
        spec: LaunchSpec,
        *,
        probe_health_fn: Callable[..., dict[str, object]],
    ) -> RuntimeStatusPayload:
        """Inspect Docker state, then delegate status resolution."""

        inspect_result = self.shell_runner(
            ["docker", "inspect", spec.container_name, "--format", "{{json .State}}"],
            timeout=30,
        )
        return self.status_support.status(
            spec,
            state=self._inspect_state(inspect_result),
            probe_health=probe_health_fn,
            stderr=inspect_result.stderr,
        )

    def probe_health(
        self,
        endpoint: str,
        *,
        health_timeout_seconds: float,
    ) -> dict[str, object]:
        """Probe agent HTTP health endpoint with runtime-compatible payloads."""

        url = f"{endpoint.rstrip('/')}/healthz"
        try:
            with urlrequest.urlopen(url, timeout=health_timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8") or "{}")
        except urlerror.HTTPError as error:
            return {
                "ok": False,
                "status_code": error.code,
                "error": error.reason,
            }
        except Exception as error:
            return {
                "ok": False,
                "status_code": None,
                "error": str(error),
            }
        if isinstance(payload, dict):
            return {
                "ok": True,
                "status_code": _HTTP_OK,
                "payload": payload,
            }
        return {
            "ok": True,
            "status_code": _HTTP_OK,
            "payload": {"raw": payload},
        }

    @staticmethod
    def _inspect_state(result: ShellResult) -> dict[str, object] | None:
        if result.returncode != 0:
            return None
        payload = json.loads(result.stdout.strip() or "{}")
        if not isinstance(payload, dict):
            return {}
        return cast(dict[str, object], payload)

    def _remove_container(self, container_name: str, *, remove: bool) -> bool:
        if not remove:
            return False
        checked_command(
            self.shell_runner,
            ["docker", "rm", "-f", container_name],
            timeout=120,
            error_message=f"failed to remove {container_name}",
        )
        return True


@dataclass(frozen=True)
class DockerImageSupport:
    shell_runner: ShellCommandRunner
    build_context_root: Path
    auto_build_local_images: bool

    def ensure_image_available(self, image: str) -> None:
        normalized = str(image).strip()
        if not normalized or self.image_exists(normalized):
            return
        dockerfile_name = backend_profiles.local_runtime_dockerfile(normalized)
        if dockerfile_name is None:
            return
        if not self.auto_build_local_images:
            raise RuntimeError(f"docker image {normalized} is missing and auto-build is disabled")
        dockerfile_path = (self.build_context_root / dockerfile_name).resolve()
        if not dockerfile_path.exists():
            raise RuntimeError(
                "docker image "
                f"{normalized} is missing and build dockerfile was not found: {dockerfile_path}"
            )
        checked_command(
            self.shell_runner,
            [
                "docker",
                "build",
                "-f",
                str(dockerfile_path),
                "-t",
                normalized,
                str(self.build_context_root),
            ],
            timeout=1800,
            error_message=f"failed to build local runtime image {normalized}",
        )

    def image_exists(self, image: str) -> bool:
        return self.shell_runner(["docker", "image", "inspect", image], timeout=60).returncode == 0


@dataclass(frozen=True)
class DockerCommandFactory:
    healthcheck_shell_type: str

    def build_run_command(self, spec: LaunchSpec) -> list[str]:
        command = [
            "docker",
            "run",
            "-d",
            "--name",
            spec.container_name,
            "--restart",
            "no",
        ]
        command.extend(self.label_flags(spec))
        if spec.working_dir is not None:
            command.extend(["--workdir", spec.working_dir])
        command.extend(self.env_flags(spec))
        command.extend(self.healthcheck_flags(spec))
        command.extend(self.mount_flags(spec))
        if spec.default_network:
            command.extend(["--network", spec.default_network])
        if spec.entrypoint:
            command.extend(["--entrypoint", spec.entrypoint])
        command.append(spec.image)
        command.extend(spec.command)
        return command

    @staticmethod
    def label_flags(spec: LaunchSpec) -> list[str]:
        flags: list[str] = []
        for key, value in spec.labels:
            flags.extend(["--label", f"{key}={value}"])
        return flags

    @staticmethod
    def env_flags(spec: LaunchSpec) -> list[str]:
        flags: list[str] = []
        for key, value in spec.env:
            flags.extend(["-e", f"{key}={value}"])
        return flags

    def healthcheck_flags(self, spec: LaunchSpec) -> list[str]:
        command = self.docker_healthcheck_command(spec)
        if command is None:
            return []
        return [
            "--health-cmd",
            command,
            "--health-interval",
            spec.healthcheck.interval,
            "--health-timeout",
            spec.healthcheck.timeout,
            "--health-start-period",
            spec.healthcheck.start_period,
            "--health-retries",
            str(spec.healthcheck.retries),
        ]

    def docker_healthcheck_command(self, spec: LaunchSpec) -> str | None:
        test = spec.healthcheck.test
        if len(test) < 2:
            return None
        if test[0] != self.healthcheck_shell_type:
            return " ".join(test)
        return test[1]

    @staticmethod
    def mount_flags(spec: LaunchSpec) -> list[str]:
        flags: list[str] = []
        for mount in spec.mounts:
            flags.extend(["-v", f"{mount.source}:{mount.target}:{mount.mode}"])
        return flags


@dataclass(frozen=True)
class DockerLifecycleSupport:
    shell_runner: ShellCommandRunner
    command_factory: DockerCommandFactory
    image_support: DockerImageSupport
    transport_support: DockerTransportSupport

    def container_exists(self, container_name: str) -> bool:
        return self.transport_support.container_exists(container_name)

    def start_existing(
        self,
        spec: LaunchSpec,
        *,
        status_loader: Callable[[LaunchSpec], RuntimeStatusPayload],
    ) -> RuntimeActionResult:
        if not self.transport_support.container_running(spec.container_name):
            checked_command(
                self.shell_runner,
                ["docker", "start", spec.container_name],
                timeout=120,
                error_message=f"failed to start {spec.container_name}",
            )
        return RuntimeActionResult(
            action="start",
            container_name=spec.container_name,
            success=True,
            message="container already exists",
            status=status_loader(spec),
        )

    def start_new(
        self,
        spec: LaunchSpec,
        *,
        status_loader: Callable[[LaunchSpec], RuntimeStatusPayload],
    ) -> RuntimeActionResult:
        self.image_support.ensure_image_available(spec.image)
        checked_command(
            self.shell_runner,
            self.command_factory.build_run_command(spec),
            timeout=300,
            error_message=f"failed to start {spec.slug}",
        )
        return RuntimeActionResult(
            action="start",
            container_name=spec.container_name,
            success=True,
            status=status_loader(spec),
        )

    def restart(
        self,
        spec: LaunchSpec,
        *,
        status_loader: Callable[[LaunchSpec], RuntimeStatusPayload],
    ) -> RuntimeActionResult:
        if not self.container_exists(spec.container_name):
            return self.start_new(spec, status_loader=status_loader)
        checked_command(
            self.shell_runner,
            ["docker", "stop", spec.container_name],
            timeout=120,
            error_message=f"failed to stop {spec.container_name}",
        )
        checked_command(
            self.shell_runner,
            ["docker", "rm", "-f", spec.container_name],
            timeout=120,
            error_message=f"failed to remove {spec.container_name}",
        )
        self.image_support.ensure_image_available(spec.image)
        checked_command(
            self.shell_runner,
            self.command_factory.build_run_command(spec),
            timeout=300,
            error_message=f"failed to start {spec.slug}",
        )
        return RuntimeActionResult(
            action="restart",
            container_name=spec.container_name,
            success=True,
            message="container recreated",
            status=status_loader(spec),
        )

    def stop_result(self, spec: LaunchSpec, *, removed: bool) -> RuntimeActionResult:
        return RuntimeActionResult(
            action="stop",
            container_name=spec.container_name,
            success=True,
            removed=removed,
            status=self.transport_support.status_support.stopped_status(spec, removed=removed),
        )
