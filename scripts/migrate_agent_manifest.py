"""Migrate a legacy agent manifest to the unified schema.

Reads a manifest YAML, strips platform-managed runtime fields,
preserves backend config and agent config, and outputs the
unified manifest shape.

Usage:
    python scripts/migrate_agent_manifest.py --input agents/sgr/manifest.yaml --stdout
    python scripts/migrate_agent_manifest.py --input agents/sgr/manifest.yaml --output /tmp/out.yaml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _bootstrap_src_path() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    src_root = repo_root / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))


_bootstrap_src_path()


def _migrate_manifest(input_path: Path) -> str:
    from core.orchestra_agents.backend_migration_support import (
        ManifestMigrator,
        format_manifest_yaml,
        load_manifest_payload,
    )

    raw = load_manifest_payload(input_path)
    migrated = ManifestMigrator().migrate(raw)
    return format_manifest_yaml(migrated)


def _write_output(args: argparse.Namespace, output_text: str) -> None:
    if args.stdout:
        sys.stdout.write(output_text)
        return
    output_path = args.output
    assert isinstance(output_path, Path)
    output_path.write_text(output_text, encoding="utf-8")
    sys.stderr.write(f"Migrated manifest written to {output_path}\n")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate legacy agent manifest to unified schema",
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Path to input manifest.yaml",
    )
    output_group = parser.add_mutually_exclusive_group(required=True)
    output_group.add_argument(
        "--output",
        type=Path,
        help="Path to write migrated manifest",
    )
    output_group.add_argument(
        "--stdout",
        action="store_true",
        help="Print migrated manifest to stdout",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Entry point for the migration script."""
    args = _parse_args(argv)
    _write_output(args, _migrate_manifest(args.input))


if __name__ == "__main__":
    main()
