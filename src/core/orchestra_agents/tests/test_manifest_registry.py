from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.orchestra_agents.errors import ManifestValidationError
from core.orchestra_agents.manifest import AgentManifest
from core.orchestra_agents.registry import AgentManifestRegistry


class AgentManifestTests(unittest.TestCase):
    def test_normalizes_nested_manifest(self) -> None:
        manifest = AgentManifest.from_dict(
            {
                "slug": "coding_agent",
                "display_name": "Coding Agent",
                "status": "active",
                "agent": {
                    "working_dir": "/workspace",
                    "http_endpoint": "http://orchestra-agent-coding_agent:8787",
                    "system_prompt_file": "system_prompt.md",
                },
                "runtime": {
                    "driver": "docker",
                    "image": "agent-image:latest",
                    "command": [
                        "python",
                        "-m",
                        "core.orchestra_agents.backends.example.main",
                    ],
                    "mounts": [
                        {
                            "type": "bind",
                            "source": ".",
                            "target": "/workspace",
                            "mode": "rw",
                        }
                    ],
                    "env": {"AGENT_HTTP_PORT": "8787"},
                },
                "backend": {
                    "type": "codex_framework",
                    "config": {"temperature": 0},
                },
            }
        )

        self.assertEqual(manifest.slug, "coding_agent")
        self.assertEqual(manifest.agent.system_prompt_file, "system_prompt.md")
        self.assertEqual(manifest.runtime.image, "agent-image:latest")
        self.assertEqual(manifest.backend.type, "codex_framework")

    def test_normalizes_legacy_manifest_shape(self) -> None:
        manifest = AgentManifest.from_dict(
            {
                "slug": "ops_agent",
                "display_name": "Ops Agent",
                "status": "active",
                "backend_type": "sgr",
                "working_dir": "/workspace",
                "system_prompt_file": "system_prompt.md",
                "http_endpoint": "http://orchestra-agent-ops_agent:8787",
                "container": {
                    "image": "agent-image:latest",
                    "extra_env": {"LOG_LEVEL": "INFO"},
                    "volumes": [
                        {
                            "source": "/tmp",
                            "target": "/workspace/tmp",
                            "read_only": True,
                        }
                    ],
                },
            }
        )

        self.assertEqual(manifest.backend.type, "sgr")
        self.assertEqual(manifest.agent.http_endpoint, "http://orchestra-agent-ops_agent:8787")
        self.assertEqual(manifest.runtime.mounts[0].mode, "ro")
        self.assertEqual(manifest.runtime.env["LOG_LEVEL"], "INFO")

    def test_rejects_invalid_manifest(self) -> None:
        with self.assertRaises(ManifestValidationError):
            AgentManifest.from_dict({"slug": "broken"})


class AgentManifestRegistryTests(unittest.TestCase):
    def test_reports_duplicate_slugs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_duplicate_manifests(root)

            registry = AgentManifestRegistry(manifests_root=root)

            self.assertEqual(len(registry.manifests()), 1)
            self.assertEqual(len(registry.issues()), 1)
            self.assertIn("duplicate slug", registry.issues()[0].error)

    def _write_duplicate_manifests(self, root: Path) -> None:
        payload = """
slug: duplicate_agent
display_name: Duplicate Agent
status: active
agent:
  working_dir: /workspace
  http_endpoint: http://duplicate:8787
runtime:
  driver: docker
  image: agent:latest
backend:
  type: example
"""
        for dir_name in ("first", "second"):
            manifest_dir = root / dir_name
            manifest_dir.mkdir()
            (manifest_dir / "manifest.yaml").write_text(payload, encoding="utf-8")
