"""Manifest registry owned by the orchestra_agents lifecycle service."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from core.orchestra_agents.manifest import AgentManifest


@dataclass(frozen=True)
class ManifestLoadIssue:
    """One manifest path that failed to load."""

    manifest_path: str
    error: str
    slug_hint: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "manifest_path": self.manifest_path,
            "error": self.error,
            "slug_hint": self.slug_hint,
        }


@dataclass(frozen=True)
class _RegistryState:
    manifests: dict[str, AgentManifest]
    issues: list[ManifestLoadIssue]


class _RegistryLoading:
    @staticmethod
    def resolve_manifests_root(manifests_root: str | Path | None) -> Path:
        root = (
            manifests_root
            or os.getenv("ORCHESTRA_AGENTS_MANIFESTS_DIR")
            or os.path.join(os.getcwd(), "agents")
        )
        return Path(root).expanduser().resolve()

    @staticmethod
    def missing_root_state(manifests_root: Path) -> _RegistryState:
        issue = ManifestLoadIssue(
            manifest_path=str(manifests_root),
            error="manifests root does not exist",
        )
        return _RegistryState(manifests={}, issues=[issue])

    @staticmethod
    def load_one_manifest(
        path: Path,
        manifests: dict[str, AgentManifest],
        issues: list[ManifestLoadIssue],
        seen: dict[str, str],
    ) -> None:
        try:
            manifest = AgentManifest.from_file(path)
        except Exception as exc:
            issues.append(ManifestLoadIssue(manifest_path=str(path), error=str(exc)))
            return
        dup = seen.get(manifest.slug)
        if dup is not None:
            issues.append(
                ManifestLoadIssue(
                    manifest_path=str(path),
                    slug_hint=manifest.slug,
                    error=f"duplicate slug {manifest.slug!r}; first seen in {dup}",
                )
            )
            return
        seen[manifest.slug] = str(path)
        manifests[manifest.slug] = manifest

    @classmethod
    def scan_manifests(
        cls,
        root: Path,
        manifests: dict[str, AgentManifest],
        issues: list[ManifestLoadIssue],
    ) -> None:
        seen: dict[str, str] = {}
        for path in sorted(root.glob("*/manifest.yaml")):
            cls.load_one_manifest(path, manifests, issues, seen)

    @classmethod
    def build_registry_state(cls, manifests_root: Path) -> _RegistryState:
        if not manifests_root.exists():
            return cls.missing_root_state(manifests_root)

        manifests: dict[str, AgentManifest] = {}
        issues: list[ManifestLoadIssue] = []
        cls.scan_manifests(manifests_root, manifests, issues)
        return _RegistryState(manifests=manifests, issues=issues)


class _RegistryQueries:
    """Read-only query methods for the manifest registry."""

    _manifests: dict[str, AgentManifest]
    _issues: list[ManifestLoadIssue]
    manifests_root: Path

    def manifests(self) -> list[AgentManifest]:
        return list(self._manifests.values())

    def active_manifests(self) -> list[AgentManifest]:
        return [m for m in self._manifests.values() if m.is_active]

    def auto_start_manifests(self) -> list[AgentManifest]:
        return [m for m in self._manifests.values() if m.is_active and m.auto_start]

    def issues(self) -> list[ManifestLoadIssue]:
        return list(self._issues)

    def get(self, slug: str) -> AgentManifest | None:
        return self._manifests.get(str(slug).strip())

    def require(self, slug: str) -> AgentManifest:
        manifest = self.get(slug)
        if manifest is None:
            raise KeyError(f"Unknown agent slug: {slug}")
        return manifest

    def summary(self) -> dict[str, object]:
        return {
            "manifests_root": str(self.manifests_root),
            "manifest_count": len(self._manifests),
            "active_manifest_count": len(self.active_manifests()),
            "issue_count": len(self._issues),
            "issues": [item.to_dict() for item in self._issues],
        }


class AgentManifestRegistry(_RegistryQueries):
    """Load, validate, and query manifest files from a local directory."""

    def __init__(self, manifests_root: str | Path | None = None) -> None:
        self.manifests_root = _RegistryLoading.resolve_manifests_root(manifests_root)
        self._manifests: dict[str, AgentManifest] = {}
        self._issues: list[ManifestLoadIssue] = []
        self.reload()

    def reload(self) -> None:
        """Reload all manifests from disk."""
        state = _RegistryLoading.build_registry_state(self.manifests_root)
        self._manifests = state.manifests
        self._issues = state.issues
