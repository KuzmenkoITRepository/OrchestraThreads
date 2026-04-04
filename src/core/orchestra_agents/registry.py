"""Manifest registry owned by the orchestra_agents lifecycle service."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .manifest import AgentManifest


@dataclass(frozen=True)
class ManifestLoadIssue:
    """One manifest path that failed to load."""

    manifest_path: str
    error: str
    slug_hint: Optional[str] = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "manifest_path": self.manifest_path,
            "error": self.error,
            "slug_hint": self.slug_hint,
        }


class AgentManifestRegistry:
    """Load, validate, and query manifest files from a local directory."""

    def __init__(self, manifests_root: Optional[str | Path] = None) -> None:
        root = manifests_root or os.getenv("ORCHESTRA_AGENTS_MANIFESTS_DIR") or os.path.join(os.getcwd(), "agents")
        self.manifests_root = Path(root).expanduser().resolve()
        self._manifests: dict[str, AgentManifest] = {}
        self._issues: list[ManifestLoadIssue] = []
        self.reload()

    def reload(self) -> None:
        manifests: dict[str, AgentManifest] = {}
        issues: list[ManifestLoadIssue] = []
        if not self.manifests_root.exists():
            self._manifests = {}
            self._issues = [
                ManifestLoadIssue(
                    manifest_path=str(self.manifests_root),
                    error="manifests root does not exist",
                )
            ]
            return

        seen_slugs: dict[str, str] = {}
        for manifest_path in sorted(self.manifests_root.glob("*/manifest.yaml")):
            try:
                manifest = AgentManifest.from_file(manifest_path)
            except Exception as exc:
                issues.append(
                    ManifestLoadIssue(
                        manifest_path=str(manifest_path),
                        error=str(exc),
                    )
                )
                continue
            duplicate_path = seen_slugs.get(manifest.slug)
            if duplicate_path is not None:
                issues.append(
                    ManifestLoadIssue(
                        manifest_path=str(manifest_path),
                        slug_hint=manifest.slug,
                        error=f"duplicate slug {manifest.slug!r}; first seen in {duplicate_path}",
                    )
                )
                continue
            seen_slugs[manifest.slug] = str(manifest_path)
            manifests[manifest.slug] = manifest

        self._manifests = manifests
        self._issues = issues

    def manifests(self) -> list[AgentManifest]:
        return list(self._manifests.values())

    def active_manifests(self) -> list[AgentManifest]:
        return [item for item in self._manifests.values() if item.is_active]

    def issues(self) -> list[ManifestLoadIssue]:
        return list(self._issues)

    def get(self, slug: str) -> Optional[AgentManifest]:
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
