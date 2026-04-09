"""Backend switch preparation and verification entry points."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.orchestra_agents import _migration_types as migration_types
from core.orchestra_agents._migration_manifest import (
    ManifestMigrator,
    create_manifest_snapshot,
    format_manifest_yaml,
)
from core.orchestra_agents._migration_switch_config import (
    DEFAULT_SWITCH_PREPARE_MAX_MS,
    controlled_config,
    validate_supported,
    validate_switch_source,
)
from core.orchestra_agents._migration_switch_verify import (
    ResolvedHooks,
    execute_verification,
    resolve_hooks,
)
from core.orchestra_agents.manifest import AgentManifest


def prepare_backend_switch(
    manifest_path: Path,
    *,
    target_backend: str,
    temp_root: Path,
    snapshot_path: Path | None = None,
    max_prepare_ms: float = DEFAULT_SWITCH_PREPARE_MAX_MS,
) -> migration_types.BackendSwitchSummary:
    """Prepare a controlled temporary manifest for backend switching."""
    validate_supported(target_backend)
    source = AgentManifest.from_file(manifest_path)
    validate_switch_source(source)
    started = time.perf_counter()
    written = _write_switch_manifests(
        source,
        target_backend,
        temp_root,
        snapshot_path,
    )
    elapsed = (time.perf_counter() - started) * 1000.0
    return migration_types.BackendSwitchSummary(
        agent_slug=source.slug,
        source_manifest_path=manifest_path,
        temp_manifest_path=written.temp_path,
        snapshot_path=written.snap_path,
        source_backend=source.backend.type,
        target_backend=target_backend,
        mutated_fields=("backend.type",),
        elapsed_ms=elapsed,
        max_prepare_ms=max_prepare_ms,
        threshold_ok=elapsed <= max_prepare_ms,
        runtime=migration_types.runtime_summary(written.switched),
    )


def verify_backend_switch(
    manifest_path: Path,
    *,
    target_backend: str,
    temp_root: Path,
    options: object | None = None,
    hooks: ResolvedHooks | None = None,
) -> migration_types.BackendSwitchSummary:
    """Prepare, restart, and probe the narrow backend-switch subset."""
    snapshot_value = getattr(options, "snapshot_path", None)
    snapshot_path = snapshot_value if isinstance(snapshot_value, Path) else None
    max_prepare_ms = float(
        getattr(options, "max_prepare_ms", DEFAULT_SWITCH_PREPARE_MAX_MS),
    )
    prepared = prepare_backend_switch(
        manifest_path,
        target_backend=target_backend,
        temp_root=temp_root,
        snapshot_path=snapshot_path,
        max_prepare_ms=max_prepare_ms,
    )
    resolved_hooks = hooks or resolve_hooks(prepared.temp_manifest_path)
    return execute_verification(prepared, resolved_hooks)


def build_controlled_switch_payload(
    manifest: AgentManifest,
) -> dict[str, Any]:
    """Create a narrow, controlled unified payload for switch testing."""
    migrated = ManifestMigrator().migrate(manifest.to_dict())
    backend = dict(migrated.get("backend") or {})
    backend["config"] = controlled_config(manifest.backend.config)
    migrated["backend"] = backend
    return migrated


@dataclass(frozen=True)
class _SwitchWriteResult:
    temp_path: Path
    snap_path: Path
    switched: AgentManifest


def _write_switch_manifests(
    source: AgentManifest,
    target_backend: str,
    temp_root: Path,
    snapshot_path: Path | None,
) -> _SwitchWriteResult:
    controlled = build_controlled_switch_payload(source)
    temp_path = temp_root.resolve() / source.slug / "manifest.yaml"
    ctrl_text = format_manifest_yaml(controlled)
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path.write_text(ctrl_text, encoding="utf-8")
    snap = create_manifest_snapshot(
        temp_path,
        snapshot_path=snapshot_path,
        source_bytes=ctrl_text.encode("utf-8"),
    )
    return _apply_target(controlled, target_backend, temp_path, snap)


def _apply_target(
    controlled: dict[str, Any],
    target_backend: str,
    temp_path: Path,
    snap: Path,
) -> _SwitchWriteResult:
    switched = dict(controlled)
    backend = dict(switched.get("backend") or {})
    backend["type"] = target_backend
    switched["backend"] = backend
    text = format_manifest_yaml(switched)
    temp_path.write_text(text, encoding="utf-8")
    manifest = AgentManifest.from_yaml_text(
        text,
        manifest_path=temp_path,
    )
    return _SwitchWriteResult(temp_path, snap, manifest)
