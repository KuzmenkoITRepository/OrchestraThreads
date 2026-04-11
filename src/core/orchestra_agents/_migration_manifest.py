"""Manifest IO and migration helpers for backend migration support."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class _ManifestMigrationHelpers:
    missing_sentinel = object()

    @classmethod
    def migrate_manifest_payload(cls, raw: dict[str, Any]) -> dict[str, Any]:
        migrated = dict(raw)
        migrated = cls.normalize_backend_block(migrated)
        migrated = cls.normalize_agent_block(migrated)
        migrated.pop("runtime", None)
        cls.strip_legacy_fields(migrated)
        return migrated

    @classmethod
    def normalize_agent_block(cls, manifest: dict[str, Any]) -> dict[str, Any]:
        result = dict(manifest)
        result["agent"] = cls.build_agent_block(manifest, result.get("agent"))
        return result

    @classmethod
    def build_agent_block(
        cls,
        manifest: dict[str, Any],
        agent_payload: Any,
    ) -> dict[str, Any]:
        normalized_agent = dict(agent_payload) if isinstance(agent_payload, dict) else {}
        for key in (
            "working_dir",
            "http_endpoint",
            "system_prompt_file",
        ):
            if key in manifest and key not in normalized_agent:
                normalized_agent[key] = manifest[key]
        clean = {
            field_name: normalized_agent[field_name]
            for field_name in ("working_dir", "http_endpoint")
            if normalized_agent.get(field_name, cls.missing_sentinel) is not cls.missing_sentinel
        }
        system_prompt_file = normalized_agent.get("system_prompt_file")
        if system_prompt_file:
            clean["system_prompt_file"] = system_prompt_file
        allowed_peer_agent_slugs = normalized_agent.get("allowed_peer_agent_slugs")
        if allowed_peer_agent_slugs:
            clean["allowed_peer_agent_slugs"] = list(allowed_peer_agent_slugs)
        return clean

    @classmethod
    def normalize_backend_block(cls, manifest: dict[str, Any]) -> dict[str, Any]:
        result = dict(manifest)
        backend_payload = result.get("backend")
        backend = dict(backend_payload) if isinstance(backend_payload, dict) else {}
        if "backend_type" in manifest and "type" not in backend:
            backend["type"] = manifest["backend_type"]
        result["backend"] = backend
        return result

    @staticmethod
    def strip_legacy_fields(manifest: dict[str, Any]) -> None:
        for key in (
            "working_dir",
            "http_endpoint",
            "system_prompt_file",
            "backend_type",
            "container",
        ):
            manifest.pop(key, None)

    @staticmethod
    def resolve_snapshot_path(manifest_path: Path, snapshot_path: Path | None) -> Path:
        if snapshot_path is None:
            return manifest_path.with_name(f"{manifest_path.name}.snapshot")
        return snapshot_path.resolve()

    @staticmethod
    def read_snapshot_source(manifest_path: Path, source_bytes: bytes | None) -> bytes:
        if source_bytes is None:
            return manifest_path.read_bytes()
        return source_bytes


class ManifestMigrator:
    """Converts legacy manifest payloads into unified schema shape."""

    def migrate(self, raw: dict[str, Any]) -> dict[str, Any]:
        return _ManifestMigrationHelpers.migrate_manifest_payload(raw)


def load_manifest_payload(path: Path) -> dict[str, Any]:
    """Load raw manifest YAML into a mapping."""
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} does not contain a YAML mapping")
    return dict(loaded)


def format_manifest_yaml(manifest: dict[str, Any]) -> str:
    """Render manifest payload as YAML."""
    return yaml.dump(
        manifest,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )


def create_manifest_snapshot(
    manifest_path: Path,
    *,
    snapshot_path: Path | None = None,
    source_bytes: bytes | None = None,
) -> Path:
    """Store exact manifest bytes for rollback."""
    resolved = _ManifestMigrationHelpers.resolve_snapshot_path(manifest_path, snapshot_path)
    raw = _ManifestMigrationHelpers.read_snapshot_source(manifest_path, source_bytes)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_bytes(raw)
    return resolved


def restore_manifest_snapshot(
    snapshot_path: Path,
    manifest_path: Path,
) -> int:
    """Restore exact bytes from a snapshot file."""
    raw = snapshot_path.read_bytes()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(raw)
    return len(raw)


def write_migrated_output(
    manifest_path: Path,
    *,
    output_path: Path | None,
    snapshot_path: Path | None,
    migrated_text: str,
) -> Path | None:
    """Optionally write migrated manifest and create a snapshot."""
    if output_path is None:
        return None
    resolved_output = output_path.resolve()
    written: Path | None = None
    if resolved_output == manifest_path.resolve():
        written = create_manifest_snapshot(
            manifest_path,
            snapshot_path=snapshot_path,
        )
    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    resolved_output.write_text(migrated_text, encoding="utf-8")
    return written
