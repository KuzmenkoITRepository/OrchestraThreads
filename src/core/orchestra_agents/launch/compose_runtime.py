"""Compose-backed launch runtime over pure launch specs."""

from __future__ import annotations

import json
import subprocess
from functools import partial
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest

from core.orchestra_agents.launch._compose_runtime_helpers import (
    ComposeCommandFactory,
    ComposeContainerSupport,
    ComposeFileSupport,
    ComposeImageSupport,
    ComposeLifecycleSupport,
    ComposeTransportSupport,
)
from core.orchestra_agents.launch._runtime_shell import ShellCommandRunner, ShellResult
from core.orchestra_agents.launch._runtime_status import RuntimeStatusSupport
from core.orchestra_agents.launch.launch_spec import (
    LaunchSpec,
    RuntimeActionResult,
    RuntimeStatusPayload,
)


def _default_shell_runner(command: list[str], *, timeout: int = 120) -> ShellResult:
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return ShellResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _read_health_payload(url: str, *, timeout: float) -> object:
    with urlrequest.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8") or "{}")


class ComposeRuntime:
    """Launch runtime that manages compose-backed agent containers."""

    def __init__(
        self,
        *,
        compose_project_name: str,
        shell_runner: ShellCommandRunner = _default_shell_runner,
        health_timeout_seconds: float = 2,
        auto_build_local_images: bool = True,
        build_context_root: str | Path = ".",
    ) -> None:
        normalized_project_name = str(compose_project_name).strip()
        if not normalized_project_name:
            raise ValueError("compose_project_name is required")
        self.compose_project_name = normalized_project_name
        self._shell_runner = shell_runner
        self.health_timeout_seconds = max(0.2, float(health_timeout_seconds))
        self._read_health_payload = partial(
            _read_health_payload,
            timeout=self.health_timeout_seconds,
        )
        self._status_support = RuntimeStatusSupport(
            health_timeout_seconds=self.health_timeout_seconds,
        )
        self._command_factory = ComposeCommandFactory(
            compose_project_name=self.compose_project_name,
        )
        self._file_support = ComposeFileSupport(command_factory=self._command_factory)
        self._container_support = ComposeContainerSupport(
            shell_runner=self._shell_runner,
            command_factory=self._command_factory,
        )
        self._transport = ComposeTransportSupport(
            shell_runner=self._shell_runner,
            command_factory=self._command_factory,
            status_support=self._status_support,
        )
        self._image_support = ComposeImageSupport(
            shell_runner=self._shell_runner,
            build_context_root=Path(build_context_root).expanduser().resolve(),
            auto_build_local_images=bool(auto_build_local_images),
        )
        self._lifecycle = ComposeLifecycleSupport(
            file_support=self._file_support,
            container_support=self._container_support,
            transport_support=self._transport,
            image_support=self._image_support,
            status_support=self._status_support,
        )

    def container_name(self, spec: LaunchSpec) -> str:
        return spec.container_name

    def start(self, spec: LaunchSpec) -> RuntimeActionResult:
        return self._lifecycle.start(spec, status_loader=self.status)

    def stop(self, spec: LaunchSpec, *, remove: bool = False) -> RuntimeActionResult:
        return self._lifecycle.stop(spec, remove=remove)

    def restart(self, spec: LaunchSpec) -> RuntimeActionResult:
        return self._lifecycle.restart(spec, status_loader=self.status)

    def status(self, spec: LaunchSpec) -> RuntimeStatusPayload:
        return self._transport.inspect_status(spec, probe_health_fn=self._probe_health)

    def _probe_health(self, endpoint: str) -> dict[str, object]:
        url = f"{endpoint.rstrip('/')}/healthz"
        try:
            payload = self._read_health_payload(url)
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
                "status_code": 200,
                "payload": payload,
            }
        return {
            "ok": True,
            "status_code": 200,
            "payload": {"raw": payload},
        }
