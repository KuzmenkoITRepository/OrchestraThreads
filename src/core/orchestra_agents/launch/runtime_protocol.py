"""Runtime protocol for pure launch specs."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.orchestra_agents.launch.launch_spec import (
    LaunchSpec,
    RuntimeActionResult,
    RuntimeStatusPayload,
)


@runtime_checkable
class ContainerRuntime(Protocol):
    """Container lifecycle interface over pure launch specs."""

    def container_name(self, spec: LaunchSpec) -> str:
        """Resolve exact container name for spec."""
        ...

    def start(self, spec: LaunchSpec) -> RuntimeActionResult:
        """Start container for spec."""
        ...

    def stop(self, spec: LaunchSpec, *, remove: bool = False) -> RuntimeActionResult:
        """Stop container for spec."""
        ...

    def restart(self, spec: LaunchSpec) -> RuntimeActionResult:
        """Restart container for spec."""
        ...

    def status(self, spec: LaunchSpec) -> RuntimeStatusPayload:
        """Return runtime status payload for spec."""
        ...
