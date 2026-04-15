"""Private builder configuration helpers for launch spec builder."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, Unpack

from core.orchestra_agents import _docker_driver_support as driver_support


@dataclass(frozen=True)
class BuilderPaths:
    """Resolved filesystem/config paths used by launch spec builder."""

    manifests_root: Path
    host_manifests_root: Path
    manifest_mount_path: str
    compose_runtime_dir: Path


@dataclass(frozen=True)
class BuilderConfig:
    """Normalized launch spec builder configuration."""

    paths: BuilderPaths
    container_name_prefix: str
    default_network: str | None


class BuilderInitKwargs(TypedDict, total=False):
    """Keyword arguments supported by launch spec builder init."""

    manifests_root: str | Path | None
    host_manifests_root: str | Path | None
    container_name_prefix: str
    default_network: str | None
    manifest_mount_path: str
    compose_runtime_dir: str | Path | None


def resolve_builder_config(
    *,
    paths: BuilderPaths | None = None,
    **kwargs: Unpack[BuilderInitKwargs],
) -> BuilderConfig:
    """Resolve builder config from init kwargs."""

    resolved_paths = paths or _resolve_paths(
        manifests_root=kwargs.get("manifests_root"),
        host_manifests_root=kwargs.get("host_manifests_root"),
        manifest_mount_path=kwargs.get("manifest_mount_path", "/orchestra/agents"),
        compose_runtime_dir=kwargs.get("compose_runtime_dir"),
    )
    return BuilderConfig(
        paths=resolved_paths,
        container_name_prefix=str(kwargs.get("container_name_prefix", "orchestra-agent-")),
        default_network=str(kwargs.get("default_network") or "").strip() or None,
    )


def _resolve_paths(
    *,
    manifests_root: str | Path | None,
    host_manifests_root: str | Path | None,
    manifest_mount_path: str,
    compose_runtime_dir: str | Path | None,
) -> BuilderPaths:
    if manifests_root is None:
        raise ValueError("manifests_root is required")
    resolved_manifests_root = Path(manifests_root).expanduser().resolve()
    resolved_host_root = _resolve_host_root(host_manifests_root, resolved_manifests_root)
    resolved_compose_dir = _resolve_compose_runtime_dir(
        compose_runtime_dir,
        resolved_manifests_root,
    )
    return BuilderPaths(
        manifests_root=resolved_manifests_root,
        host_manifests_root=resolved_host_root,
        manifest_mount_path=str(manifest_mount_path).rstrip("/"),
        compose_runtime_dir=resolved_compose_dir,
    )


def _resolve_host_root(host_manifests_root: str | Path | None, manifests_root: Path) -> Path:
    if host_manifests_root is None:
        return manifests_root
    return Path(host_manifests_root).expanduser().resolve()


def _resolve_compose_runtime_dir(
    compose_runtime_dir: str | Path | None,
    manifests_root: Path,
) -> Path:
    if compose_runtime_dir is None:
        return (manifests_root.parent / driver_support.COMPOSE_RUNTIME_DIRNAME).resolve()
    return Path(compose_runtime_dir).expanduser().resolve()
