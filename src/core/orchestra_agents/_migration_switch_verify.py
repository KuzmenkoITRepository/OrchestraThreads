"""Verification execution for backend switch operations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.orchestra_agents._migration_contract import (
    default_contract_probe,
    probe_runtime_contract,
    status_ok,
)
from core.orchestra_agents._migration_types import BackendSwitchSummary
from core.orchestra_agents.manifest import AgentManifest
from core.orchestra_agents.service_state import ServiceState


@dataclass(frozen=True)
class ResolvedHooks:
    """Resolved hook callables for switch verification."""

    restart: Callable[[AgentManifest], dict[str, Any]]
    status: Callable[[AgentManifest], dict[str, Any]]
    probe: Callable[
        [str, str, dict[str, Any] | None],
        dict[str, Any],
    ]
    name_fn: Callable[[str], str]


@dataclass(frozen=True)
class _ServiceStateVerificationHooks:
    """Migration-specific verification hooks backed by service seams."""

    state: ServiceState

    @classmethod
    def from_manifest_path(
        cls,
        manifest_path: Path,
    ) -> _ServiceStateVerificationHooks:
        return cls(
            state=ServiceState.create(
                manifests_root=str(manifest_path.parent.parent),
            ),
        )

    def restart(self, manifest: AgentManifest) -> dict[str, Any]:
        return self._runtime_action(manifest, operation="restart")

    def status(self, manifest: AgentManifest) -> dict[str, Any]:
        return self._runtime_action(manifest, operation="status")

    def container_name(self, slug: str) -> str:
        manifest = self.state.require_manifest(slug)
        return self.state.build_spec(manifest).container_name

    def _runtime_action(
        self,
        manifest: AgentManifest,
        *,
        operation: str,
    ) -> dict[str, Any]:
        spec = self.state.build_spec(manifest)
        runtime = self.state.resolve_runtime(spec, operation=operation)
        if operation == "restart":
            return runtime.restart(spec).to_dict()
        return runtime.status(spec).to_dict()


def resolve_hooks(
    manifest_path: Path,
    restart_agent: Callable[
        [AgentManifest],
        dict[str, Any],
    ]
    | None = None,
    status_agent: Callable[
        [AgentManifest],
        dict[str, Any],
    ]
    | None = None,
    contract_probe: Callable[
        [str, str, dict[str, Any] | None],
        dict[str, Any],
    ]
    | None = None,
    container_name_for: Callable[[str], str] | None = None,
) -> ResolvedHooks:
    """Build resolved hooks from optional overrides or defaults."""
    service_hooks = _ServiceStateVerificationHooks.from_manifest_path(
        manifest_path,
    )
    return ResolvedHooks(
        restart=restart_agent or service_hooks.restart,
        status=status_agent or service_hooks.status,
        probe=contract_probe or default_contract_probe,
        name_fn=container_name_for or service_hooks.container_name,
    )


def execute_verification(
    prepared: BackendSwitchSummary,
    hooks: ResolvedHooks,
) -> BackendSwitchSummary:
    """Run restart, status, and contract probes."""
    switched = AgentManifest.from_file(
        prepared.temp_manifest_path,
    )
    restart_res = hooks.restart(switched)
    status_res = hooks.status(switched)
    contract = probe_runtime_contract(
        switched,
        container_name=hooks.name_fn(switched.slug),
        probe=hooks.probe,
    )
    ok = status_ok(status_res) and bool(contract["ok"])
    return _rebuild(
        prepared,
        ok,
        restart_res,
        status_res,
        contract,
    )


def _rebuild(
    prepared: BackendSwitchSummary,
    verified: bool,
    restart_result: dict[str, Any],
    status_result: dict[str, Any],
    contract_checks: dict[str, Any],
) -> BackendSwitchSummary:
    return BackendSwitchSummary(
        agent_slug=prepared.agent_slug,
        source_manifest_path=prepared.source_manifest_path,
        temp_manifest_path=prepared.temp_manifest_path,
        snapshot_path=prepared.snapshot_path,
        source_backend=prepared.source_backend,
        target_backend=prepared.target_backend,
        mutated_fields=prepared.mutated_fields,
        elapsed_ms=prepared.elapsed_ms,
        max_prepare_ms=prepared.max_prepare_ms,
        threshold_ok=prepared.threshold_ok,
        runtime=prepared.runtime,
        verified=verified,
        execution_mode="restart_probe",
        restart_result=restart_result,
        status_result=status_result,
        contract_checks=contract_checks,
    )
