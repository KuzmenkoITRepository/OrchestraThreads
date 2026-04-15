"""Docker CLI runtime over pure launch specs."""

from __future__ import annotations

import os
import subprocess
from functools import partial
from pathlib import Path

from core.orchestra_agents.launch._docker_cli_helpers import (
    DockerCommandFactory,
    DockerImageSupport,
    DockerLifecycleSupport,
    DockerTransportSupport,
)
from core.orchestra_agents.launch._runtime_shell import (
    ShellCommandRunner,
    ShellResult,
)
from core.orchestra_agents.launch._runtime_status import RuntimeStatusSupport
from core.orchestra_agents.launch.launch_spec import (
    LaunchSpec,
    RuntimeActionResult,
    RuntimeStatusPayload,
)

_HEALTHCHECK_SHELL_TYPE = "CMD-SHELL"


def _subprocess_runner(command: list[str], *, timeout: int = 120) -> ShellResult:
    """Default shell boundary for Docker CLI commands."""

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


class DockerCliRuntime:
    """Start, stop, restart, inspect containers with Docker CLI only."""

    def __init__(
        self,
        *,
        shell_runner: ShellCommandRunner = _subprocess_runner,
        build_context_root: str | Path | None = None,
        health_timeout_seconds: float = 2,
        auto_build_local_images: bool = True,
    ) -> None:
        self._shell_runner = shell_runner
        self.health_timeout_seconds = max(0.2, health_timeout_seconds)
        self.auto_build_local_images = bool(auto_build_local_images)
        raw_build_root = (
            build_context_root or os.getenv("ORCHESTRA_AGENTS_IMAGE_BUILD_CONTEXT") or "."
        )
        self._build_context_root = Path(raw_build_root).expanduser().resolve()
        self._status_support = RuntimeStatusSupport(
            health_timeout_seconds=self.health_timeout_seconds,
        )
        self._transport = DockerTransportSupport(
            shell_runner=self._shell_runner,
            status_support=self._status_support,
        )
        self._probe_health = partial(
            self._transport.probe_health,
            health_timeout_seconds=self.health_timeout_seconds,
        )
        self._lifecycle = DockerLifecycleSupport(
            shell_runner=self._shell_runner,
            command_factory=DockerCommandFactory(
                healthcheck_shell_type=_HEALTHCHECK_SHELL_TYPE,
            ),
            image_support=DockerImageSupport(
                shell_runner=self._shell_runner,
                build_context_root=self._build_context_root,
                auto_build_local_images=self.auto_build_local_images,
            ),
            transport_support=self._transport,
        )

    def container_name(self, spec: LaunchSpec) -> str:
        """Return stable container name from spec."""

        return spec.container_name

    def start(self, spec: LaunchSpec) -> RuntimeActionResult:
        """Start container from spec, reusing existing container when possible."""

        if self._lifecycle.container_exists(spec.container_name):
            return self._lifecycle.start_existing(spec, status_loader=self.status)
        return self._lifecycle.start_new(spec, status_loader=self.status)

    def stop(self, spec: LaunchSpec, *, remove: bool = False) -> RuntimeActionResult:
        """Stop container, optionally removing it."""

        if not self._lifecycle.container_exists(spec.container_name):
            return self._lifecycle.stop_result(spec, removed=False)
        return self._transport.stop_container(spec, remove=remove)

    def restart(self, spec: LaunchSpec) -> RuntimeActionResult:
        """Restart by removing existing container, then starting fresh."""

        return self._lifecycle.restart(spec, status_loader=self.status)

    def status(self, spec: LaunchSpec) -> RuntimeStatusPayload:
        """Inspect current runtime state with Docker-first health precedence."""

        return self._transport.inspect_status(spec, probe_health_fn=self._probe_health)
