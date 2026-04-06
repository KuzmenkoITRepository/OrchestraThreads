from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.orchestra_agents.scaffold import ScaffoldOptions, scaffold_agent


class ScaffoldAgentTests(unittest.TestCase):
    def test_scaffold_agent_renders_placeholders(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "coding_agent"
            scaffold_agent(
                slug="coding_agent",
                output_dir=output_dir,
                options=ScaffoldOptions(
                    display_name="Coding Agent",
                    backend_type="codex_framework",
                ),
            )

            manifest_text = (output_dir / "manifest.yaml").read_text(encoding="utf-8")
            main_text = (output_dir / "agent_runtime" / "main.py").read_text(encoding="utf-8")
            self.assertIn("slug: coding_agent", manifest_text)
            self.assertIn("type: codex_framework", manifest_text)
            self.assertIn("Coding Agent", manifest_text)
            self.assertIn("coding_agent", main_text)

    def test_scaffold_mux_template_creates_wrappers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "thread_worker"
            scaffold_agent(
                slug="thread_worker",
                output_dir=output_dir,
                options=ScaffoldOptions(
                    display_name="Thread Worker",
                    backend_type="agent_mux",
                    template="agent_mux",
                ),
            )

            manifest_text = (output_dir / "manifest.yaml").read_text(encoding="utf-8")
            backend_text = (output_dir / "agent_runtime" / "backend.py").read_text(encoding="utf-8")

            self.assertIn("slug: thread_worker", manifest_text)
            self.assertIn("type: agent_mux", manifest_text)
            self.assertIn("Generic event-driven compatibility wrapper", backend_text)
            self._assert_generated_configs(output_dir)

    def _assert_generated_configs(self, output_dir: Path) -> None:
        self.assertTrue((output_dir / ".agent-mux" / "config.toml").exists())
        self.assertTrue((output_dir / ".codex" / "config.toml").exists())
