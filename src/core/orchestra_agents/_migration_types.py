"""Shared data types for backend migration support."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.orchestra_agents.docker_driver import resolve_backend_runtime
from core.orchestra_agents.manifest import AgentManifest


@dataclass(frozen=True)
class RuntimeResolutionSummary:
    """Machine-readable runtime evidence for a manifest."""

    image: str
    command: tuple[str, ...]
    entrypoint: str | None
    env: dict[str, str]
    env_passthrough: tuple[str, ...]
    http_endpoint: str

    def to_dict(self) -> dict[str, object]:
        return {
            "image": self.image,
            "command": list(self.command),
            "entrypoint": self.entrypoint,
            "env": dict(self.env),
            "env_passthrough": list(self.env_passthrough),
            "http_endpoint": self.http_endpoint,
        }


@dataclass(frozen=True)
class MigrationCheckSummary:
    """Verification result for a manifest migration."""

    agent_slug: str
    manifest_path: Path
    source_backend: str
    migrated_backend: str
    source_runtime: RuntimeResolutionSummary
    migrated_runtime: RuntimeResolutionSummary
    output_path: Path | None
    snapshot_path: Path | None
    switch_subset_supported: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "agent_slug": self.agent_slug,
            "manifest_path": str(self.manifest_path),
            "source_backend": self.source_backend,
            "migrated_backend": self.migrated_backend,
            "source_runtime": self.source_runtime.to_dict(),
            "migrated_runtime": self.migrated_runtime.to_dict(),
            "output_path": _optional_path(self.output_path),
            "snapshot_path": _optional_path(self.snapshot_path),
            "switch_subset_supported": self.switch_subset_supported,
            "supported_subset": (
                "controlled temporary manifests only; clean-state restart required"
            ),
        }


@dataclass(frozen=True)
class BackendSwitchSummary:
    """Prepared backend switch evidence for the supported subset."""

    agent_slug: str
    source_manifest_path: Path
    temp_manifest_path: Path
    snapshot_path: Path
    source_backend: str
    target_backend: str
    mutated_fields: tuple[str, ...]
    elapsed_ms: float
    max_prepare_ms: float
    threshold_ok: bool
    runtime: RuntimeResolutionSummary
    verified: bool = False
    execution_mode: str = "prepare_only"
    restart_result: dict[str, Any] | None = None
    status_result: dict[str, Any] | None = None
    contract_checks: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, object]:
        return _switch_summary_dict(self)


@dataclass(frozen=True)
class SwitchPrepareOptions:
    """Optional inputs for backend switch preparation/verification."""

    snapshot_path: Path | None = None
    max_prepare_ms: float = 1500.0


def runtime_summary(manifest: AgentManifest) -> RuntimeResolutionSummary:
    """Build runtime resolution evidence from a manifest."""
    resolved = resolve_backend_runtime(manifest)
    return RuntimeResolutionSummary(
        image=resolved.image,
        command=tuple(resolved.command),
        entrypoint=resolved.entrypoint,
        env=dict(resolved.env),
        env_passthrough=tuple(resolved.env_passthrough),
        http_endpoint=manifest.resolve_http_endpoint(),
    )


def _optional_path(path: Path | None) -> str | None:
    return str(path) if path else None


def _switch_summary_dict(
    summary: BackendSwitchSummary,
) -> dict[str, object]:
    return {
        "agent_slug": summary.agent_slug,
        "source_manifest_path": str(summary.source_manifest_path),
        "temp_manifest_path": str(summary.temp_manifest_path),
        "snapshot_path": str(summary.snapshot_path),
        "source_backend": summary.source_backend,
        "target_backend": summary.target_backend,
        "mutated_fields": list(summary.mutated_fields),
        "elapsed_ms": round(summary.elapsed_ms, 3),
        "max_prepare_ms": summary.max_prepare_ms,
        "threshold_ok": summary.threshold_ok,
        "verified": summary.verified,
        "restart_required": True,
        "clean_state_only": True,
        "execution_mode": summary.execution_mode,
        "mutation_scope": "controlled_temp_manifest",
        "supported_subset": (
            "controlled temporary manifests only; validate contract"
            " surfaces and platform-derived runtime defaults"
        ),
        "runtime": summary.runtime.to_dict(),
        "restart_result": summary.restart_result,
        "status_result": summary.status_result,
        "contract_checks": summary.contract_checks,
    }
