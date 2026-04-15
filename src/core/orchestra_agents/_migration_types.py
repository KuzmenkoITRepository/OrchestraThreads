"""Shared data types for backend migration support."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.orchestra_agents.manifest import AgentManifest
from core.orchestra_agents.service_state import ServiceState


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
            "output_path": str(self.output_path) if self.output_path else None,
            "snapshot_path": str(self.snapshot_path) if self.snapshot_path else None,
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
        return {
            "agent_slug": self.agent_slug,
            "source_manifest_path": str(self.source_manifest_path),
            "temp_manifest_path": str(self.temp_manifest_path),
            "snapshot_path": str(self.snapshot_path),
            "source_backend": self.source_backend,
            "target_backend": self.target_backend,
            "mutated_fields": list(self.mutated_fields),
            "elapsed_ms": round(self.elapsed_ms, 3),
            "max_prepare_ms": self.max_prepare_ms,
            "threshold_ok": self.threshold_ok,
            "verified": self.verified,
            "restart_required": True,
            "clean_state_only": True,
            "execution_mode": self.execution_mode,
            "mutation_scope": "controlled_temp_manifest",
            "supported_subset": (
                "controlled temporary manifests only; validate contract"
                " surfaces and platform-derived runtime defaults"
            ),
            "runtime": self.runtime.to_dict(),
            "restart_result": self.restart_result,
            "status_result": self.status_result,
            "contract_checks": self.contract_checks,
        }


@dataclass(frozen=True)
class SwitchPrepareOptions:
    """Optional inputs for backend switch preparation/verification."""

    snapshot_path: Path | None = None
    max_prepare_ms: float = 1500.0


@dataclass(frozen=True)
class _RuntimeEvidenceBuilder:
    """Service-state-backed runtime evidence builder."""

    state: ServiceState

    @classmethod
    def from_manifest(cls, manifest: AgentManifest) -> _RuntimeEvidenceBuilder:
        manifest_path = _require_manifest_path(manifest)
        return cls(
            state=ServiceState.create(
                manifests_root=str(manifest_path.parent.parent),
            ),
        )

    def build(self, manifest: AgentManifest) -> RuntimeResolutionSummary:
        spec = self.state.build_spec(manifest)
        resolved = self.state.builder.runtime_profile(manifest)
        return RuntimeResolutionSummary(
            image=resolved.image,
            command=tuple(resolved.command),
            entrypoint=resolved.entrypoint,
            env=dict(resolved.env),
            env_passthrough=tuple(resolved.env_passthrough),
            http_endpoint=manifest.resolve_http_endpoint(
                container_name=spec.container_name,
            ),
        )


def runtime_summary(manifest: AgentManifest) -> RuntimeResolutionSummary:
    """Build runtime evidence from launch profile resolution."""
    return _RuntimeEvidenceBuilder.from_manifest(manifest).build(manifest)


def _require_manifest_path(manifest: AgentManifest) -> Path:
    manifest_path = manifest.manifest_path
    if manifest_path is None:
        raise RuntimeError(
            "runtime summary requires manifest_path for launch builder resolution",
        )
    return manifest_path
