"""Tests for strict manifest parsing and backend validation."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any

from core.orchestra_agents.errors import ManifestValidationError
from core.orchestra_agents.manifest import AgentManifest

_REPO_ROOT = Path(__file__).resolve().parents[4]

_EXISTING_MANIFESTS = (
    "agents/dev/manifest.yaml",
    "agents/devops/manifest.yaml",
    "agents/qa/manifest.yaml",
    "agents/sgr/manifest.yaml",
    "agents/orchestra/manifest.yaml",
    "agents/opencode-example/manifest.yaml",
    "agents/secretary/manifest.yaml",
    "agents/whiner/manifest.yaml",
)


class _ManifestValidationBase(unittest.TestCase):
    def _minimal_manifest(
        self,
        *,
        backend_type: str = "sgr_minimax",
        config: dict[str, Any] | None = None,
        image: str | None = None,
    ) -> dict[str, Any]:
        raw: dict[str, Any] = {
            "slug": "test-agent",
            "display_name": "Test Agent",
            "status": "active",
            "agent": {
                "working_dir": "/workspace",
                "http_endpoint": "http://{container_name}:8787",
            },
            "backend": {
                "type": backend_type,
                "config": config or {"route_policy": "x", "model": "y"},
            },
        }
        if image is not None:
            raw["runtime"] = {"image": image}
        return raw

    def _parse_manifest_error(self, raw: dict[str, Any]) -> str:
        try:
            AgentManifest.from_dict(raw)
        except ManifestValidationError as error:
            return str(error)
        raise AssertionError("expected ManifestValidationError")

    def _parse_manifest(self, raw: dict[str, Any]) -> AgentManifest:
        return AgentManifest.from_dict(raw)

    def _warning_output(self, raw: dict[str, Any]) -> list[str]:
        with self.assertLogs(
            "core.orchestra_agents._backend_validation",
            level="WARNING",
        ) as captured_logs:
            AgentManifest.from_dict(raw)
            warning_lines = list(captured_logs.output)
        return warning_lines


class TestExistingManifestsValidate(_ManifestValidationBase):
    """All existing agent manifests must still parse after changes."""

    def test_all_existing_manifests_parse(self) -> None:
        for rel_path in _EXISTING_MANIFESTS:
            full_path = _REPO_ROOT / rel_path
            with self.subTest(manifest=rel_path):
                manifest = AgentManifest.from_file(full_path)
                self.assertTrue(manifest.slug)
                self.assertTrue(manifest.backend.type)

    def test_secretary_manifest_http_mcp(self) -> None:
        manifest = AgentManifest.from_file(_REPO_ROOT / "agents" / "secretary" / "manifest.yaml")

        telegram_relay = next(
            server
            for server in manifest.backend.config["mcp_servers"]
            if server["name"] == "telegram_relay"
        )

        self.assertEqual(telegram_relay["transport"], "http")


class TestUnifiedModeValidation(_ManifestValidationBase):
    """Unified manifests without runtime.image validate for known backends."""

    def test_sgr_without_image_validates(self) -> None:
        raw = self._minimal_manifest(
            backend_type="sgr_minimax",
            config={"route_policy": "x", "model": "y"},
        )
        manifest = self._parse_manifest(raw)
        self.assertEqual(manifest.backend.type, "sgr_minimax")
        self.assertEqual(manifest.runtime.image, "")

    def test_agent_mux_without_image_validates(self) -> None:
        raw = self._minimal_manifest(
            backend_type="agent_mux",
            config={"role": "worker", "llm_route_policy": "x", "model": "y"},
        )
        manifest = self._parse_manifest(raw)
        self.assertEqual(manifest.backend.type, "agent_mux")

    def test_opencode_without_image_validates(self) -> None:
        raw = self._minimal_manifest(
            backend_type="opencode_omo",
            config={"model": "y"},
        )
        manifest = self._parse_manifest(raw)
        self.assertEqual(manifest.backend.type, "opencode_omo")


class TestUnknownBackendValidation(_ManifestValidationBase):
    """Unknown backend types still validate with image, fail without."""

    def test_unknown_backend_with_image_validates(self) -> None:
        raw = self._minimal_manifest(
            backend_type="custom_backend",
            config={},
            image="my-image:latest",
        )
        manifest = self._parse_manifest(raw)
        self.assertEqual(manifest.backend.type, "custom_backend")
        self.assertEqual(manifest.runtime.image, "my-image:latest")

    def test_unknown_backend_logs_warning(self) -> None:
        raw = self._minimal_manifest(
            backend_type="custom_backend",
            config={},
            image="my-image:latest",
        )
        warning_lines = self._warning_output(raw)
        self.assertTrue(warning_lines)
        self.assertIn("custom_backend", warning_lines[0])

    def test_unknown_backend_without_image_fails(self) -> None:
        raw = self._minimal_manifest(
            backend_type="custom_backend",
            config={},
        )
        error_text = self._parse_manifest_error(raw)
        self.assertIn("runtime.image", error_text)


class TestBackendConfigValidation(_ManifestValidationBase):
    """Backend-specific config keys are validated for known backends."""

    def test_missing_required_key_fails(self) -> None:
        raw = self._minimal_manifest(
            backend_type="sgr_minimax",
            config={"route_policy": "x"},
        )
        error_text = self._parse_manifest_error(raw)
        self.assertIn("backend.config.model", error_text)

    def test_all_required_keys_present_passes(self) -> None:
        raw = self._minimal_manifest(
            backend_type="sgr_minimax",
            config={"route_policy": "x", "model": "y"},
        )
        manifest = self._parse_manifest(raw)
        self.assertEqual(manifest.backend.config["model"], "y")

    def test_optional_keys_accepted(self) -> None:
        raw = self._minimal_manifest(
            backend_type="sgr_minimax",
            config={
                "route_policy": "x",
                "model": "y",
                "temperature": 0.5,
                "max_tokens": 100,
            },
        )
        manifest = self._parse_manifest(raw)
        self.assertEqual(manifest.backend.config["temperature"], 0.5)

    def test_sgr_mcp_server_requires_inline_keys(self) -> None:
        raw = self._minimal_manifest(
            backend_type="sgr_minimax",
            config={
                "route_policy": "x",
                "model": "y",
                "mcp_servers": [{"name": "threads", "command": "python"}],
            },
        )

        error_text = self._parse_manifest_error(raw)

        self.assertIn("backend.config.mcp_servers[0].module is required", error_text)
        self.assertIn("backend.config.mcp_servers[0].class is required", error_text)
        self.assertIn("backend.config.mcp_servers[0].command is not supported", error_text)

    def test_agent_mux_mcp_server_rejects_inline_keys(self) -> None:
        raw = self._minimal_manifest(
            backend_type="agent_mux",
            config={
                "role": "worker",
                "llm_route_policy": "x",
                "model": "y",
                "mcp_servers": [
                    {
                        "name": "threads",
                        "module": "core.orchestra_thread.mcp.server",
                        "class": "OrchestraThreadsMCPServer",
                    },
                ],
            },
        )

        error_text = self._parse_manifest_error(raw)

        self.assertIn("backend.config.mcp_servers[0].command is required", error_text)
        self.assertIn("backend.config.mcp_servers[0].module is not supported", error_text)
        self.assertIn("backend.config.mcp_servers[0].class is not supported", error_text)

    def test_opencode_mcp_rejects_mux_only_keys(self) -> None:
        raw = self._minimal_manifest(
            backend_type="opencode_omo",
            config={
                "model": "y",
                "mcp_servers": [
                    {
                        "name": "threads",
                        "command": "python",
                        "cwd": "/workspace",
                    },
                ],
            },
        )

        error_text = self._parse_manifest_error(raw)

        self.assertIn("backend.config.mcp_servers[0].cwd is not supported", error_text)


class _MigrationScriptBase(unittest.TestCase):
    script_path = _REPO_ROOT / "scripts" / "migrate_agent_manifest.py"
    input_path = _REPO_ROOT / "agents" / "sgr" / "manifest.yaml"

    def _run_migration(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(self.script_path),
                "--input",
                str(self.input_path),
                "--stdout",
            ],
            capture_output=True,
            text=True,
            check=True,
        )


class TestMigrationScript(_MigrationScriptBase):
    """Migration script produces valid unified output."""

    def test_migration_produces_valid_output(self) -> None:
        result = self._run_migration()
        migrated = AgentManifest.from_yaml_text(result.stdout)
        self.assertEqual(migrated.slug, "sgr")
        self.assertEqual(migrated.backend.type, "sgr_minimax")

    def test_migration_strips_runtime(self) -> None:
        result = self._run_migration()
        self.assertNotIn("runtime:", result.stdout)
        self.assertNotIn("image:", result.stdout)
