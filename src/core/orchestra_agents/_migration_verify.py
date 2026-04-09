"""Manifest migration verification."""

from __future__ import annotations

from pathlib import Path

from core.orchestra_agents._migration_manifest import (
    ManifestMigrator,
    format_manifest_yaml,
    load_manifest_payload,
    write_migrated_output,
)
from core.orchestra_agents._migration_switch_config import (
    is_controlled_switch_ready,
)
from core.orchestra_agents._migration_types import (
    MigrationCheckSummary,
    runtime_summary,
)
from core.orchestra_agents.manifest import AgentManifest


def verify_manifest_migration(
    manifest_path: Path,
    *,
    output_path: Path | None = None,
    snapshot_path: Path | None = None,
) -> MigrationCheckSummary:
    """Verify or write a unified manifest migration."""
    source = AgentManifest.from_file(manifest_path)
    migrated_payload = ManifestMigrator().migrate(
        load_manifest_payload(manifest_path),
    )
    migrated_text = format_manifest_yaml(migrated_payload)
    migrated = AgentManifest.from_yaml_text(
        migrated_text,
        manifest_path=output_path or manifest_path,
    )
    written = write_migrated_output(
        manifest_path,
        output_path=output_path,
        snapshot_path=snapshot_path,
        migrated_text=migrated_text,
    )
    return MigrationCheckSummary(
        agent_slug=source.slug,
        manifest_path=manifest_path,
        source_backend=source.backend.type,
        migrated_backend=migrated.backend.type,
        source_runtime=runtime_summary(source),
        migrated_runtime=runtime_summary(migrated),
        output_path=output_path,
        snapshot_path=written,
        switch_subset_supported=is_controlled_switch_ready(migrated),
    )
