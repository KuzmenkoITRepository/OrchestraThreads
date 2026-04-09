"""CLI support for manifest migration verification."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from core.orchestra_agents import _migration_types as migration_types
from core.orchestra_agents.backend_migration_support import verify_manifest_migration


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify unified manifest migration for an agent",
    )
    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument("--agent", help="Agent slug under agents/<slug>/manifest.yaml")
    target_group.add_argument("--manifest", type=Path, help="Path to a manifest.yaml file")
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Validate migration without writing any manifest",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional output path for the migrated manifest",
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        help="Optional backup path when writing in-place",
    )
    return parser.parse_args(argv)


def _resolve_manifest_path(args: argparse.Namespace) -> Path:
    manifest = getattr(args, "manifest", None)
    if isinstance(manifest, Path):
        return manifest.resolve()
    repo_root = Path(__file__).resolve().parents[3]
    agent = str(getattr(args, "agent", "")).strip()
    return (repo_root / "agents" / agent / "manifest.yaml").resolve()


def _output_path(args: argparse.Namespace) -> Path | None:
    output = getattr(args, "output", None)
    return output.resolve() if isinstance(output, Path) else None


def _validate_mode(args: argparse.Namespace, output_path: Path | None) -> None:
    if bool(getattr(args, "check_only", False)):
        return
    if output_path is None:
        raise ValueError("use --check-only or provide --output")


def _verify_summary(args: argparse.Namespace) -> migration_types.MigrationCheckSummary:
    output_path = _output_path(args)
    _validate_mode(args, output_path)
    snapshot = getattr(args, "snapshot", None)
    return verify_manifest_migration(
        _resolve_manifest_path(args),
        output_path=output_path,
        snapshot_path=snapshot.resolve() if isinstance(snapshot, Path) else None,
    )


def _emit(payload: dict[str, object]) -> int:
    sys.stdout.write(f"{json.dumps(payload, sort_keys=True)}\n")
    return 0 if bool(payload.get("ok")) else 1


def run_cli(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        summary = _verify_summary(args)
    except Exception as error:  # pragma: no cover - guarded CLI path
        return _emit({"ok": False, "error": str(error)})
    return _emit({"ok": True, **summary.to_dict()})
