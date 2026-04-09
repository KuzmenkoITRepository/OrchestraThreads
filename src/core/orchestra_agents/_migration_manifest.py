"""Manifest IO and migration helpers for backend migration support."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_MISSING = object()


class ManifestMigrator:
    """Converts legacy manifest payloads into unified schema shape."""

    def migrate(self, raw: dict[str, Any]) -> dict[str, Any]:
        migrated = dict(raw)
        migrated = self._normalize_backend(migrated)
        migrated = self._normalize_agent(migrated)
        migrated.pop("runtime", None)
        self._strip_legacy_fields(migrated)
        return migrated

    def _normalize_agent(
        self,
        manifest: dict[str, Any],
    ) -> dict[str, Any]:
        result = dict(manifest)
        agent = self._extract_agent_block(result)
        result["agent"] = self._build_clean_agent(agent)
        return result

    def _build_clean_agent(
        self,
        agent: dict[str, Any],
    ) -> dict[str, Any]:
        clean: dict[str, Any] = {}
        for field_name in ("working_dir", "http_endpoint"):
            field_val = agent.get(field_name, _MISSING)
            if field_val is not _MISSING:
                clean[field_name] = field_val
        if agent.get("system_prompt_file"):
            clean["system_prompt_file"] = agent["system_prompt_file"]
        peers = agent.get("allowed_peer_agent_slugs")
        if peers:
            clean["allowed_peer_agent_slugs"] = list(peers)
        return clean

    def _normalize_backend(
        self,
        manifest: dict[str, Any],
    ) -> dict[str, Any]:
        result = dict(manifest)
        backend = _safe_dict(result, "backend")
        if "backend_type" in manifest and "type" not in backend:
            backend["type"] = manifest["backend_type"]
        result["backend"] = backend
        return result

    def _strip_legacy_fields(
        self,
        manifest: dict[str, Any],
    ) -> None:
        for key in (
            "working_dir",
            "http_endpoint",
            "system_prompt_file",
            "backend_type",
            "container",
        ):
            manifest.pop(key, None)

    def _extract_agent_block(
        self,
        manifest: dict[str, Any],
    ) -> dict[str, Any]:
        agent = _safe_dict(manifest, "agent")
        for key in (
            "working_dir",
            "http_endpoint",
            "system_prompt_file",
        ):
            if key in manifest and key not in agent:
                agent[key] = manifest[key]
        return agent


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
    if snapshot_path is None:
        resolved = manifest_path.with_name(
            f"{manifest_path.name}.snapshot",
        )
    else:
        resolved = snapshot_path.resolve()
    raw = manifest_path.read_bytes() if source_bytes is None else source_bytes
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


def _safe_dict(
    payload: dict[str, Any],
    key: str,
) -> dict[str, Any]:
    """Extract a dict sub-key, defaulting to empty dict."""
    gotten = payload.get(key)
    if isinstance(gotten, dict):
        return dict(gotten)
    return {}
