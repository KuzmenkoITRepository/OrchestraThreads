from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from typing import Any, cast

import yaml

from core.orchestra_agents._migration_switch_verify import ResolvedHooks
from core.orchestra_agents.backend_migration_support import (
    DEFAULT_SWITCH_PREPARE_MAX_MS,
    create_manifest_snapshot,
    prepare_backend_switch,
    restore_manifest_snapshot,
    verify_backend_switch,
    verify_manifest_migration,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
_SAMPLE_MANIFEST = _REPO_ROOT / "agents" / "sgr" / "manifest.yaml"
_PYTHON_BIN = _REPO_ROOT / ".venv" / "bin" / "python"
_SGR = "sgr_minimax"
_OC = "opencode_omo"
_HEALTHY = MappingProxyType(
    {"exists": True, "running": True, "healthy": True},
)


def _load_yaml(path: Path) -> dict[str, object]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


class _FakeHooks:
    """Captures restart/status/probe calls for switch tests."""

    def __init__(self) -> None:
        self.restarts: list[str] = []
        self.statuses: list[str] = []
        self.probes: list[tuple[str, str]] = []

    def restart(self, manifest: object) -> dict[str, object]:
        self.restarts.append(_btype(manifest))
        return dict(_HEALTHY)

    def status(self, manifest: object) -> dict[str, object]:
        self.statuses.append(_btype(manifest))
        return dict(_HEALTHY)

    def probe(
        self,
        url: str,
        method: str,
        payload: dict[str, object] | None,
    ) -> dict[str, object]:
        self.probes.append((method, url))
        return _probe_response(url, payload)


def _btype(manifest: object) -> str:
    backend = cast(Any, manifest).backend
    return str(backend.type)


def _probe_response(
    url: str,
    payload: dict[str, object] | None,
) -> dict[str, object]:
    base = {"ok": True, "status_code": 200}
    if url.endswith("/healthz"):
        return {**base, "payload": {"ok": True}}
    if url.endswith("/last_status"):
        return {**base, "payload": {"backend_type": _OC}}
    if url.endswith(("/clear_context", "/stop")):
        return {**base, "payload": {"success": True}}
    if url.endswith("/event"):
        assert payload is not None
        return {**base, "payload": {"accepted": True}}
    raise AssertionError(url)


class MigrationSupportTests(unittest.TestCase):
    def test_verify_migration_preserves(self) -> None:
        s = verify_manifest_migration(_SAMPLE_MANIFEST)

        self.assertEqual(s.agent_slug, "sgr")
        self.assertEqual(s.source_backend, _SGR)
        self.assertEqual(s.migrated_backend, _SGR)
        self.assertIsNone(s.output_path)
        self.assertIsNone(s.snapshot_path)
        self.assertEqual(
            s.migrated_runtime.image,
            "orchestra-sgr-runtime:latest",
        )
        self.assertTrue(s.switch_subset_supported)

    def test_prepare_switch_type_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            s = prepare_backend_switch(
                _SAMPLE_MANIFEST,
                target_backend=_OC,
                temp_root=Path(tmpdir) / "prepared",
                max_prepare_ms=DEFAULT_SWITCH_PREPARE_MAX_MS,
            )
            self.assertEqual(s.source_backend, _SGR)
            self.assertEqual(s.target_backend, _OC)
            self.assertEqual(s.mutated_fields, ("backend.type",))
            self.assertTrue(s.threshold_ok)
            self.assertLessEqual(
                s.elapsed_ms,
                DEFAULT_SWITCH_PREPARE_MAX_MS,
            )
            self._assert_backend_files(s)

    def test_verify_switch_probes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            hooks = _FakeHooks()
            s = verify_backend_switch(
                _SAMPLE_MANIFEST,
                target_backend=_OC,
                temp_root=Path(tmpdir) / "verified",
                options=SimpleNamespace(
                    snapshot_path=None,
                    max_prepare_ms=DEFAULT_SWITCH_PREPARE_MAX_MS,
                ),
                hooks=ResolvedHooks(
                    restart=hooks.restart,
                    status=hooks.status,
                    probe=hooks.probe,
                    name_fn=lambda sl: f"orchestra-agent-{sl}",
                ),
            )
            self.assertEqual(s.execution_mode, "restart_probe")
            self.assertTrue(s.verified)
            self.assertEqual(hooks.restarts, [_OC])
            self.assertEqual(hooks.statuses, [_OC])
            assert s.contract_checks is not None
            self.assertTrue(s.contract_checks["ok"])
            self.assertEqual(len(hooks.probes), 5)

    def _assert_backend_files(self, s: object) -> None:
        summary = cast(Any, s)
        snap = _load_yaml(summary.snapshot_path)
        switched = _load_yaml(
            summary.temp_manifest_path,
        )
        snap_be = snap.get("backend")
        sw_be = switched.get("backend")
        assert isinstance(snap_be, dict) and isinstance(sw_be, dict)
        self.assertEqual(snap["agent"], switched["agent"])
        self.assertEqual(snap_be, {**sw_be, "type": _SGR})


class MigrationSnapshotTests(unittest.TestCase):
    def test_migration_writes_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            mpath = Path(tmpdir) / "manifest.yaml"
            mpath.write_text(
                _SAMPLE_MANIFEST.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            s = verify_manifest_migration(
                mpath,
                output_path=mpath,
                snapshot_path=Path(tmpdir) / "manifest.snapshot",
            )
            self.assertIsNotNone(s.snapshot_path)
            assert s.snapshot_path is not None
            self.assertNotIn("runtime", _load_yaml(mpath))
            snap = _load_yaml(s.snapshot_path)
            snap_rt = snap["runtime"]
            assert isinstance(snap_rt, dict)
            self.assertEqual(
                snap_rt["image"],
                "orchestra-threads:local",
            )

    def test_snapshot_restore(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            mpath = Path(tmpdir) / "manifest.yaml"
            mpath.write_text(
                "backend:\n  type: sgr_minimax\n",
                encoding="utf-8",
            )
            original = mpath.read_bytes()
            snap = create_manifest_snapshot(mpath)
            mpath.write_text(
                "backend:\n  type: opencode_omo\n",
                encoding="utf-8",
            )
            restored = restore_manifest_snapshot(snap, mpath)
            self.assertEqual(restored, len(original))
            self.assertEqual(mpath.read_bytes(), original)


class MigrationScriptTests(unittest.TestCase):
    def test_verify_migration_script(self) -> None:
        result = subprocess.run(
            [
                str(_PYTHON_BIN),
                str(_SCRIPTS_DIR / "verify_agent_migration.py"),
                "--agent",
                "sgr",
                "--check-only",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["agent_slug"], "sgr")
        self.assertEqual(
            payload["migrated_runtime"]["image"],
            "orchestra-sgr-runtime:latest",
        )

    def test_switch_script_json(self) -> None:
        result = subprocess.run(
            [
                str(_PYTHON_BIN),
                str(_SCRIPTS_DIR / "test_backend_switch.py"),
                "--agent",
                "sgr",
                "--target-backend",
                _OC,
                "--check-only",
                "--prepare-only",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(
            payload["mutated_fields"],
            ["backend.type"],
        )
        self.assertTrue(payload["clean_state_only"])
        self.assertTrue(payload["restart_required"])
        self.assertEqual(payload["execution_mode"], "prepare_only")

    def test_switch_prepare_script(self) -> None:
        result = subprocess.run(
            [
                str(_PYTHON_BIN),
                str(_SCRIPTS_DIR / "test_backend_switch.py"),
                "--agent",
                "sgr",
                "--target-backend",
                _OC,
                "--check-only",
                "--prepare-only",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["execution_mode"], "prepare_only")

    def test_rollback_manifest_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            original = "backend:\n  type: sgr_minimax\n"
            self._run_rollback(
                tmpdir,
                original,
                "backend:\n  type: agent_mux\n",
                "rollback_agent_manifest.sh",
                "manifest.snapshot",
            )

    def test_rollback_switch_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            original = "backend:\n  type: sgr_minimax\n"
            self._run_rollback(
                tmpdir,
                original,
                "backend:\n  type: opencode_omo\n",
                "rollback_backend_switch.sh",
                "switch.snapshot",
            )

    def _run_rollback(
        self,
        tmpdir: str,
        snap_text: str,
        manifest_text: str,
        script: str,
        snap_name: str,
    ) -> None:
        temp_dir = Path(tmpdir)
        snap = temp_dir / snap_name
        mpath = temp_dir / "manifest.yaml"
        snap.write_text(snap_text, encoding="utf-8")
        mpath.write_text(manifest_text, encoding="utf-8")
        result = subprocess.run(
            [
                "bash",
                str(_SCRIPTS_DIR / script),
                str(snap),
                str(mpath),
            ],
            capture_output=True,
            text=True,
            check=True,
            cwd=_REPO_ROOT,
        )
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(
            mpath.read_text(encoding="utf-8"),
            snap_text,
        )
