"""Filesystem path helpers for launch specs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.orchestra_agents.manifest import AgentManifest


@dataclass(frozen=True)
class LaunchPathContext:
    """Filesystem context used while building launch paths."""

    manifests_root: Path
    host_manifests_root: Path
    manifest_mount_path: str


def resolve_compose_file_path(compose_runtime_dir: Path, *, slug: str) -> Path:
    """Return compose file path for an agent slug."""

    return compose_runtime_dir / f"{slug}.yaml"


def resolve_container_manifest_path(
    manifest: AgentManifest,
    *,
    path_context: LaunchPathContext,
) -> str:
    """Return container-visible manifest path."""

    manifest_path = _require_manifest_path(manifest)
    try:
        relative_path = manifest_path.relative_to(path_context.manifests_root)
    except ValueError as error:
        raise RuntimeError(
            f"manifest path {manifest_path} is outside manifests root {path_context.manifests_root}"
        ) from error
    return f"{path_context.manifest_mount_path}/{relative_path.as_posix()}"


def resolve_bind_source_path(
    manifest: AgentManifest,
    source: str,
    *,
    path_context: LaunchPathContext,
) -> Path:
    """Resolve bind source path using manifest-relative path math only."""

    source_path = Path(source)
    if source_path.is_absolute():
        resolved_path = source_path
    else:
        host_manifest_path = _host_manifest_path(
            manifest,
            path_context=path_context,
        )
        if host_manifest_path is None:
            raise RuntimeError(
                f"cannot resolve relative bind mount {source!r} without manifest path"
            )
        resolved_path = (host_manifest_path.parent / source_path).resolve()
    return resolved_path


def _host_manifest_path(
    manifest: AgentManifest,
    *,
    path_context: LaunchPathContext,
) -> Path | None:
    manifest_path = manifest.manifest_path
    if manifest_path is None:
        return None
    resolved_manifest_path = manifest_path.resolve()
    try:
        relative_path = resolved_manifest_path.relative_to(path_context.manifests_root)
    except ValueError:
        return resolved_manifest_path
    return (path_context.host_manifests_root / relative_path).resolve()


def _require_manifest_path(manifest: AgentManifest) -> Path:
    manifest_path = manifest.manifest_path
    if manifest_path is None:
        raise RuntimeError(f"manifest path is missing for {manifest.slug}")
    return manifest_path.resolve()
