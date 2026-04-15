"""Runtime env/config resolution for orchestra agents service state."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from core.orchestra_agents import _docker_driver_support as driver_support


@dataclass(frozen=True)
class ServiceRuntimeConfig:
    host_manifests_root: Path | None
    container_name_prefix: str
    default_network: str | None
    manifest_mount_path: str
    health_timeout_seconds: float
    auto_build_local_images: bool
    build_context_root: Path
    compose_runtime_dir: Path
    compose_project_name: str
    runtime_name: str | None

    @classmethod
    def from_manifests_root(cls, manifests_root: Path) -> ServiceRuntimeConfig:
        return cls(
            host_manifests_root=_configured_host_manifests_root(),
            container_name_prefix=str(
                os.getenv("ORCHESTRA_AGENTS_CONTAINER_NAME_PREFIX") or "orchestra-agent-"
            ),
            default_network=_configured_default_network(),
            manifest_mount_path=str(
                os.getenv("ORCHESTRA_AGENTS_MANIFEST_MOUNT_PATH") or "/orchestra/agents"
            ).rstrip("/"),
            health_timeout_seconds=max(
                0.2,
                float(os.getenv("ORCHESTRA_AGENTS_HEALTH_TIMEOUT_SECONDS", "2")),
            ),
            auto_build_local_images=_configured_auto_build_local_images(),
            build_context_root=Path(
                os.getenv("ORCHESTRA_AGENTS_IMAGE_BUILD_CONTEXT") or manifests_root.parent
            )
            .expanduser()
            .resolve(),
            compose_runtime_dir=Path(
                os.getenv("ORCHESTRA_AGENTS_COMPOSE_RUNTIME_DIR")
                or manifests_root.parent / driver_support.COMPOSE_RUNTIME_DIRNAME
            )
            .expanduser()
            .resolve(),
            compose_project_name=str(
                os.getenv("ORCHESTRA_AGENTS_COMPOSE_PROJECT_NAME")
                or os.getenv("COMPOSE_PROJECT_NAME")
                or "orchestrathreads"
            ).strip(),
            runtime_name=_runtime_name_from_env(),
        )


def _configured_host_manifests_root() -> Path | None:
    configured_root = os.getenv("ORCHESTRA_AGENTS_HOST_MANIFESTS_DIR")
    if configured_root is None:
        return None
    normalized_root = str(configured_root).strip()
    if not normalized_root:
        return None
    return Path(normalized_root).expanduser().resolve()


def _configured_default_network() -> str | None:
    normalized_network = str(os.getenv("ORCHESTRA_AGENTS_DOCKER_NETWORK") or "").strip()
    return normalized_network or None


def _configured_auto_build_local_images() -> bool:
    normalized = str(os.getenv("ORCHESTRA_AGENTS_AUTO_BUILD_LOCAL_IMAGES", "true")).strip().lower()
    return normalized not in {"0", "false", "no", "off"}


def _runtime_name_from_env() -> str | None:
    runtime_name = str(os.getenv("ORCHESTRA_AGENTS_RUNTIME") or "").strip().lower()
    if not runtime_name:
        return None
    if runtime_name == "docker":
        return "docker-cli"
    return runtime_name
