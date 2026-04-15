"""Helper objects for compose-backed launch runtime."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from core.orchestra_agents import _docker_driver_support as driver_support
from core.orchestra_agents.launch import backend_profiles
from core.orchestra_agents.launch._runtime_shell import (
    ShellCommandRunner,
    ShellResult,
    checked_command,
)
from core.orchestra_agents.launch._runtime_status import ProbeHealth, RuntimeStatusSupport
from core.orchestra_agents.launch.launch_spec import (
    LaunchSpec,
    RuntimeActionResult,
    RuntimeStatusPayload,
)


@dataclass(frozen=True)
class ComposeCommandFactory:
    compose_project_name: str

    def compose_command(self, compose_file: Path, *args: str) -> list[str]:
        return [
            "docker",
            "compose",
            "-p",
            self.compose_project_name,
            "-f",
            str(compose_file),
            *args,
        ]

    def compose_service_name(self, spec: LaunchSpec) -> str:
        service_name = spec.compose_service_name
        if service_name is None:
            raise RuntimeError(f"compose service name is missing for {spec.slug}")
        return service_name

    @staticmethod
    def compose_file_path(spec: LaunchSpec) -> Path:
        compose_file = spec.compose_file_path
        if compose_file is None:
            raise RuntimeError(f"compose file path is missing for {spec.slug}")
        return compose_file

    def compose_stop_command(
        self, spec: LaunchSpec, compose_file: Path, *, remove: bool
    ) -> list[str]:
        service_name = self.compose_service_name(spec)
        command = ["rm", "-sf", service_name] if remove else ["stop", service_name]
        return self.compose_command(compose_file, *command)

    def compose_payload(self, spec: LaunchSpec) -> dict[str, object]:
        service: dict[str, object] = {
            "image": spec.image,
            "container_name": spec.container_name,
            "restart": "no",
            "working_dir": spec.working_dir,
            "labels": dict(spec.labels),
            "environment": dict(spec.env),
            "healthcheck": spec.healthcheck.to_dict(),
            "volumes": self.compose_volumes(spec),
            "command": list(spec.command),
        }
        if spec.entrypoint:
            service["entrypoint"] = spec.entrypoint
        payload: dict[str, object] = {"services": {self.compose_service_name(spec): service}}
        if spec.default_network:
            payload["networks"] = {
                "default": {
                    "name": spec.default_network,
                    "external": True,
                },
            }
        return payload

    @staticmethod
    def compose_volumes(spec: LaunchSpec) -> list[str]:
        return [f"{mount.source}:{mount.target}:{mount.mode}" for mount in spec.mounts]


@dataclass(frozen=True)
class ComposeFileSupport:
    command_factory: ComposeCommandFactory

    def write_compose_file(self, spec: LaunchSpec) -> Path:
        compose_file = self.command_factory.compose_file_path(spec)
        compose_file.parent.mkdir(
            parents=True,
            exist_ok=True,
            mode=driver_support.COMPOSE_RUNTIME_DIR_MODE,
        )
        os.chmod(compose_file.parent, driver_support.COMPOSE_RUNTIME_DIR_MODE)
        compose_file.write_text(
            json.dumps(self.command_factory.compose_payload(spec), indent=2),
            encoding="utf-8",
        )
        os.chmod(compose_file, driver_support.COMPOSE_RUNTIME_FILE_MODE)
        return compose_file

    def ensure_compose_metadata(
        self,
        spec: LaunchSpec,
        compose_file: Path,
        *,
        container_exists: bool,
        remove: bool,
    ) -> None:
        if compose_file.exists():
            return
        if remove and not container_exists:
            return
        raise RuntimeError(
            f"compose metadata missing for compose-managed agent {spec.slug}: {compose_file}"
        )

    @staticmethod
    def cleanup_compose_file(compose_file: Path, *, remove: bool) -> None:
        if remove and compose_file.exists():
            compose_file.unlink()


@dataclass(frozen=True)
class ComposeContainerSupport:
    shell_runner: ShellCommandRunner
    command_factory: ComposeCommandFactory

    def container_exists(self, container_name: str) -> bool:
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
        return container_name in {
            line.strip() for line in result.stdout.splitlines() if line.strip()
        }

    def remove_legacy_container_if_needed(self, spec: LaunchSpec) -> None:
        if not self.container_exists(spec.container_name):
            return
        if self.container_matches_compose_service(spec):
            return
        checked_command(
            self.shell_runner,
            ["docker", "rm", "-f", spec.container_name],
            timeout=120,
            error_message=f"failed to replace {spec.container_name}",
        )

    def container_matches_compose_service(self, spec: LaunchSpec) -> bool:
        labels = self.container_labels(spec.container_name)
        if not labels:
            return False
        return labels.get(
            driver_support.COMPOSE_PROJECT_LABEL
        ) == self.command_factory.compose_project_name and (
            labels.get(driver_support.COMPOSE_SERVICE_LABEL)
            == self.command_factory.compose_service_name(spec)
        )

    def container_labels(self, container_name: str) -> dict[str, str]:
        result = self.shell_runner(
            ["docker", "inspect", container_name, "--format", "{{json .Config.Labels}}"],
            timeout=30,
        )
        if result.returncode != 0:
            return {}
        raw_labels = json.loads(result.stdout.strip() or "{}")
        if not isinstance(raw_labels, dict):
            return {}
        return {str(key): str(value) for key, value in raw_labels.items()}

    def stop_result(self, spec: LaunchSpec, *, removed: bool) -> RuntimeActionResult:
        return RuntimeActionResult(
            action="stop",
            container_name=spec.container_name,
            success=True,
            removed=removed,
            status=None,
        )


@dataclass(frozen=True)
class ComposeTransportSupport:
    shell_runner: ShellCommandRunner
    command_factory: ComposeCommandFactory
    status_support: RuntimeStatusSupport

    def start_service(self, spec: LaunchSpec, compose_file: Path, *, recreate: bool) -> None:
        command_args = ["up", "-d"]
        if recreate:
            command_args.append("--force-recreate")
        command_args.extend(["--no-deps", self.command_factory.compose_service_name(spec)])
        self._run_checked(
            self.command_factory.compose_command(compose_file, *command_args),
            timeout=300,
            error_message=self._start_error_message(spec, recreate=recreate),
        )

    def stop_service(self, spec: LaunchSpec, compose_file: Path, *, remove: bool) -> None:
        self._run_checked(
            self.command_factory.compose_stop_command(spec, compose_file, remove=remove),
            timeout=120,
            error_message=f"failed to stop {spec.container_name}",
        )

    def inspect_status(
        self,
        spec: LaunchSpec,
        *,
        probe_health_fn: ProbeHealth,
    ) -> RuntimeStatusPayload:
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

    def _run_checked(
        self,
        command: list[str],
        *,
        timeout: int,
        error_message: str,
    ) -> None:
        checked_command(
            self.shell_runner,
            command,
            timeout=timeout,
            error_message=error_message,
        )

    @staticmethod
    def _inspect_state(result: ShellResult) -> dict[str, object] | None:
        if result.returncode != 0:
            return None
        payload = json.loads(result.stdout.strip() or "{}")
        if not isinstance(payload, dict):
            return {}
        return cast(dict[str, object], payload)

    @staticmethod
    def _start_error_message(spec: LaunchSpec, *, recreate: bool) -> str:
        if recreate:
            return f"failed to restart {spec.slug}"
        return f"failed to start {spec.slug}"


@dataclass(frozen=True)
class ComposeLifecycleSupport:
    file_support: ComposeFileSupport
    container_support: ComposeContainerSupport
    transport_support: ComposeTransportSupport
    image_support: ComposeImageSupport
    status_support: RuntimeStatusSupport

    def start(
        self,
        spec: LaunchSpec,
        *,
        status_loader: Callable[[LaunchSpec], RuntimeStatusPayload],
    ) -> RuntimeActionResult:
        self.image_support.ensure_image_available(spec.image)
        compose_file = self.file_support.write_compose_file(spec)
        self.container_support.remove_legacy_container_if_needed(spec)
        self.transport_support.start_service(spec, compose_file, recreate=False)
        return RuntimeActionResult(
            action="start",
            container_name=spec.container_name,
            success=True,
            message="compose service ensured",
            status=status_loader(spec),
        )

    def stop(self, spec: LaunchSpec, *, remove: bool) -> RuntimeActionResult:
        compose_file = self.file_support.command_factory.compose_file_path(spec)
        container_exists = self.container_support.container_exists(spec.container_name)
        self.file_support.ensure_compose_metadata(
            spec,
            compose_file,
            container_exists=container_exists,
            remove=remove,
        )
        if not container_exists and not remove:
            return self._stop_result(spec, removed=False)
        self.transport_support.stop_service(spec, compose_file, remove=remove)
        self.file_support.cleanup_compose_file(compose_file, remove=remove)
        return self._stop_result(spec, removed=remove)

    def restart(
        self,
        spec: LaunchSpec,
        *,
        status_loader: Callable[[LaunchSpec], RuntimeStatusPayload],
    ) -> RuntimeActionResult:
        self.image_support.ensure_image_available(spec.image)
        compose_file = self.file_support.write_compose_file(spec)
        self.container_support.remove_legacy_container_if_needed(spec)
        self.transport_support.start_service(spec, compose_file, recreate=True)
        return RuntimeActionResult(
            action="restart",
            container_name=spec.container_name,
            success=True,
            message="compose service recreated",
            status=status_loader(spec),
        )

    def _stop_result(self, spec: LaunchSpec, *, removed: bool) -> RuntimeActionResult:
        result = self.container_support.stop_result(spec, removed=removed)
        return RuntimeActionResult(
            action=result.action,
            container_name=result.container_name,
            success=result.success,
            message=result.message,
            removed=result.removed,
            status=self.status_support.stopped_status(spec, removed=removed),
        )


@dataclass(frozen=True)
class ComposeImageSupport:
    shell_runner: ShellCommandRunner
    build_context_root: Path
    auto_build_local_images: bool

    def ensure_image_available(self, image: str) -> None:
        normalized_image = str(image or "").strip()
        if not normalized_image or self.image_exists(normalized_image):
            return
        dockerfile_name = backend_profiles.local_runtime_dockerfile(normalized_image)
        if dockerfile_name is None:
            return
        if not self.auto_build_local_images:
            raise RuntimeError(
                f"docker image {normalized_image} is missing and auto-build is disabled"
            )
        dockerfile_path = (self.build_context_root / dockerfile_name).resolve()
        if not dockerfile_path.exists():
            raise RuntimeError(
                "docker image "
                f"{normalized_image} is missing and build dockerfile was not found: {dockerfile_path}"
            )
        checked_command(
            self.shell_runner,
            [
                "docker",
                "build",
                "-f",
                str(dockerfile_path),
                "-t",
                normalized_image,
                str(self.build_context_root),
            ],
            timeout=1800,
            error_message=f"failed to build local runtime image {normalized_image}",
        )

    def image_exists(self, image: str) -> bool:
        result = self.shell_runner(["docker", "image", "inspect", image], timeout=60)
        return result.returncode == 0
