"""CLI support for controlled backend-switch verification."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from core.orchestra_agents import _migration_types as migration_types
from core.orchestra_agents.backend_migration_support import (
    DEFAULT_SWITCH_PREPARE_MAX_MS,
    prepare_backend_switch,
    verify_backend_switch,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare a controlled temporary manifest for backend switch verification",
    )
    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument("--agent", help="Agent slug under agents/<slug>/manifest.yaml")
    target_group.add_argument("--manifest", type=Path, help="Path to a manifest.yaml file")
    parser.add_argument("--target-backend", required=True, help="Target backend.type value")
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Use an ephemeral temp root and validate without preserving files",
    )
    parser.add_argument(
        "--temp-root",
        type=Path,
        help="Directory that will receive the controlled temporary manifest",
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        help="Optional explicit snapshot path for the controlled manifest",
    )
    parser.add_argument(
        "--max-prepare-ms",
        type=float,
        default=DEFAULT_SWITCH_PREPARE_MAX_MS,
        help="Conservative acceptance-path latency guardrail in milliseconds",
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Only prepare the controlled temp manifest without restart/probe verification",
    )
    return parser.parse_args(argv)


def _resolve_manifest_path(args: argparse.Namespace) -> Path:
    manifest = getattr(args, "manifest", None)
    if isinstance(manifest, Path):
        return manifest.resolve()
    repo_root = Path(__file__).resolve().parents[3]
    agent = str(getattr(args, "agent", "")).strip()
    return (repo_root / "agents" / agent / "manifest.yaml").resolve()


def _resolve_temp_root(args: argparse.Namespace) -> Path:
    if bool(getattr(args, "check_only", False)):
        return Path(tempfile.mkdtemp(prefix="backend-switch-"))
    temp_root = getattr(args, "temp_root", None)
    if not isinstance(temp_root, Path):
        raise ValueError("provide --temp-root unless --check-only is set")
    return temp_root.resolve()


def _switch_options(args: argparse.Namespace) -> migration_types.SwitchPrepareOptions:
    snapshot = getattr(args, "snapshot", None)
    snapshot_path = snapshot.resolve() if isinstance(snapshot, Path) else None
    return migration_types.SwitchPrepareOptions(
        snapshot_path=snapshot_path,
        max_prepare_ms=float(args.max_prepare_ms),
    )


def _run_switch(args: argparse.Namespace) -> migration_types.BackendSwitchSummary:
    manifest_path = _resolve_manifest_path(args)
    target_backend = str(getattr(args, "target_backend", "")).strip()
    temp_root = _resolve_temp_root(args)
    options = _switch_options(args)
    if bool(getattr(args, "prepare_only", False)):
        return prepare_backend_switch(
            manifest_path,
            target_backend=target_backend,
            temp_root=temp_root,
            snapshot_path=options.snapshot_path,
            max_prepare_ms=options.max_prepare_ms,
        )
    return verify_backend_switch(
        manifest_path,
        target_backend=target_backend,
        temp_root=temp_root,
        options=options,
    )


def _emit(payload: dict[str, object]) -> int:
    sys.stdout.write(f"{json.dumps(payload, sort_keys=True)}\n")
    return 0 if bool(payload.get("ok")) else 1


def run_cli(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        summary = _run_switch(args)
    except Exception as error:  # pragma: no cover - guarded CLI path
        return _emit({"ok": False, "error": str(error)})
    payload = summary.to_dict()
    ok = bool(payload.get("threshold_ok"))
    if not bool(getattr(args, "prepare_only", False)):
        ok = ok and bool(payload.get("verified"))
    return _emit({"ok": ok, **payload})
