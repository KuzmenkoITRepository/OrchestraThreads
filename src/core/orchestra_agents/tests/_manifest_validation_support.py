from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
EXISTING_MANIFESTS = (
    "agents/dev/manifest.yaml",
    "agents/devops/manifest.yaml",
    "agents/qa/manifest.yaml",
    "agents/sgr/manifest.yaml",
    "agents/orchestra/manifest.yaml",
    "agents/opencode-example/manifest.yaml",
    "agents/secretary/manifest.yaml",
    "agents/whiner/manifest.yaml",
)


def _candidate_repo_paths(rel_path: Path) -> tuple[Path, ...]:
    candidate_roots = (
        REPO_ROOT,
        Path.cwd().resolve(),
        *Path(__file__).resolve().parents,
    )
    seen: set[Path] = set()
    candidates: list[Path] = []
    for root in candidate_roots:
        resolved = (root / rel_path).resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        candidates.append(resolved)
    return tuple(candidates)


def resolve_repo_path(*relative_parts: str) -> Path:
    rel_path = Path(*relative_parts)
    for candidate in _candidate_repo_paths(rel_path):
        if candidate.exists():
            return candidate
    return (REPO_ROOT / rel_path).resolve()
