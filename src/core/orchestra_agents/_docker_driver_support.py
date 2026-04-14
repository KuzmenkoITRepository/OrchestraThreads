"""Support types and constants for the Docker driver."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict


@dataclass(frozen=True)
class StatusContext:
    """Resolved status lookup context for a managed container."""

    slug: str
    backend_type: str | None
    endpoint: str | None
    container_name: str


class InitOptions(TypedDict, total=False):
    """Optional Docker driver initialization overrides."""

    container_name_prefix: str | None
    default_network: str | None
    manifest_mount_path: str | None
    host_manifests_root: str | Path | None
    health_timeout_seconds: float | None
    build_context_root: str | Path | None
    auto_build_local_images: bool | None
    compose_project_name: str | None
    compose_runtime_dir: str | Path | None


JSONDict = dict[str, Any]
HealthResult = tuple[JSONDict | None, bool, str | None, bool]
LabelMap = dict[str, str]

COMPOSE_SERVICE_PREFIX = "agent-"
COMPOSE_RUNTIME_DIRNAME = ".orchestra_agents_compose"
COMPOSE_PROJECT_LABEL = "com.docker.compose.project"
COMPOSE_SERVICE_LABEL = "com.docker.compose.service"
COMPOSE_RUNTIME_DIR_MODE = 0o777
COMPOSE_RUNTIME_FILE_MODE = 0o666
