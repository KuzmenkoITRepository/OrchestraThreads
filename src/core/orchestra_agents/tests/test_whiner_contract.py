from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from core.orchestra_agents.templates.opencode.agent_runtime.config_mcp import build_mcp_block


def _load_whiner_manifest() -> dict[str, object]:
    manifest_path = Path("agents/whiner/manifest.yaml")
    loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


class WhinerContractTests(unittest.TestCase):
    def test_manifest_exposes_mcp_servers(self) -> None:
        manifest = _load_whiner_manifest()
        backend = manifest["backend"]
        assert isinstance(backend, dict)
        config = backend["config"]
        assert isinstance(config, dict)

        with tempfile.TemporaryDirectory() as tmpdir:
            payload = build_mcp_block(
                config_dir=Path(tmpdir),
                cfg=config,
                agent_slug="whiner",
                working_dir="/workspace/agents/whiner",
            )

        self.assertIn("orchestra_threads", payload)
        self.assertIn("task_registry", payload)
        self.assertIn("docker_mcp", payload)

    def test_prompt_requires_task_creation(self) -> None:
        prompt_text = Path("agents/whiner/system_prompt.md").read_text(encoding="utf-8")

        self.assertIn("create improvement tasks autonomously", prompt_text)
        self.assertIn("Assign created improvement tasks to `orchestra`", prompt_text)
        self.assertIn("agent_status(agent_slug)", prompt_text)
        self.assertIn("Do not create tasks without a concrete finding", prompt_text)
