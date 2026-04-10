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
from core.orchestra_agents.docker_driver.driver import DockerDriver
from core.orchestra_agents.manifest import AgentManifest


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
    driver = DockerDriver(
        manifests_root=manifest_path.parent.parent,
    )
    return ResolvedHooks(
        restart=restart_agent or driver.restart,
        status=status_agent or driver.status,
        probe=contract_probe or default_contract_probe,
        name_fn=container_name_for or driver.container_name,
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
