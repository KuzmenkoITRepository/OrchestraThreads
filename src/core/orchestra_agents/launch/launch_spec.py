"""Pure launch contract types for orchestra agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ResolvedMount:
    """Resolved container mount entry."""

    type: str
    source: str
    target: str
    mode: str = "rw"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "source": self.source,
            "target": self.target,
            "mode": self.mode,
        }


@dataclass(frozen=True)
class ResolvedHealthcheck:
    """Resolved healthcheck defaults for a launch spec."""

    test: tuple[str, ...] = ()
    interval: str = "30s"
    timeout: str = "5s"
    start_period: str = "10s"
    retries: int = 3

    def to_dict(self) -> dict[str, Any]:
        return {
            "test": list(self.test),
            "interval": self.interval,
            "timeout": self.timeout,
            "start_period": self.start_period,
            "retries": self.retries,
        }


@dataclass(frozen=True)
class LaunchSpec:
    """Pure launch description for a managed agent container."""

    slug: str
    container_name: str
    image: str
    labels: tuple[tuple[str, str], ...] = ()
    env: tuple[tuple[str, str], ...] = ()
    mounts: tuple[ResolvedMount, ...] = ()
    command: tuple[str, ...] = ()
    entrypoint: str | None = None
    working_dir: str | None = None
    default_network: str | None = None
    healthcheck: ResolvedHealthcheck = field(default_factory=ResolvedHealthcheck)
    compose_file_path: Path | None = None
    compose_service_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "container_name": self.container_name,
            "image": self.image,
            "labels": dict(self.labels),
            "env": dict(self.env),
            "mounts": [mount.to_dict() for mount in self.mounts],
            "command": list(self.command),
            "entrypoint": self.entrypoint,
            "working_dir": self.working_dir,
            "default_network": self.default_network,
            "healthcheck": self.healthcheck.to_dict(),
            "compose_file_path": str(self.compose_file_path) if self.compose_file_path else None,
            "compose_service_name": self.compose_service_name,
        }


@dataclass(frozen=True)
class RuntimeStatusPayload:
    """Dict-serializable runtime status payload for service reads."""

    slug: str
    container_name: str
    exists: bool
    running: bool
    healthy: bool
    backend_type: str | None = None
    http_endpoint: str | None = None
    docker_status: str | None = None
    health_status: dict[str, Any] | None = None
    started_at: str | None = None
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "container_name": self.container_name,
            "exists": self.exists,
            "running": self.running,
            "healthy": self.healthy,
            "backend_type": self.backend_type,
            "http_endpoint": self.http_endpoint,
            "docker_status": self.docker_status,
            "health_status": self.health_status,
            "started_at": self.started_at,
            "last_error": self.last_error,
        }


@dataclass(frozen=True)
class RuntimeActionResult:
    """Dict-serializable runtime action result."""

    action: str
    container_name: str
    success: bool
    message: str | None = None
    status: RuntimeStatusPayload | None = None
    removed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "container_name": self.container_name,
            "success": self.success,
            "message": self.message,
            "status": self.status.to_dict() if self.status else None,
            "removed": self.removed,
        }
