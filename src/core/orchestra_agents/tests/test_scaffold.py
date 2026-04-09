from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.orchestra_agents.scaffold import ScaffoldOptions, scaffold_agent

_UTF8 = "utf-8"


def _command_block(module_name: str) -> str:
    return f"- python\n    - -m\n    - {module_name}"


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

            manifest_text = (output_dir / "manifest.yaml").read_text(encoding=_UTF8)
            self.assertIn("slug: coding_agent", manifest_text)
            self.assertIn("type: codex_framework", manifest_text)
            self.assertIn("Coding Agent", manifest_text)
            self.assertIn(
                _command_block("core.orchestra_agents.backends.example.main"),
                manifest_text,
            )
            self.assertFalse((output_dir / "agent_runtime").exists())

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

            manifest_text = (output_dir / "manifest.yaml").read_text(encoding=_UTF8)

            self.assertIn("slug: thread_worker", manifest_text)
            self.assertIn("type: agent_mux", manifest_text)
            self.assertIn(
                _command_block("core.orchestra_agents.backends.agent_mux.main"),
                manifest_text,
            )
            self.assertFalse((output_dir / "agent_runtime").exists())
            self._assert_generated_configs(output_dir)

    def test_scaffold_opencode_creates_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "opencode_agent"
            scaffold_agent(
                slug="opencode_agent",
                output_dir=output_dir,
                options=ScaffoldOptions(
                    display_name="Opencode Agent",
                    backend_type="opencode_omo",
                    template="opencode",
                ),
            )

            manifest_text = (output_dir / "manifest.yaml").read_text(encoding=_UTF8)

            self.assertIn("slug: opencode_agent", manifest_text)
            self.assertIn("type: opencode_omo", manifest_text)
            self.assertIn(
                _command_block("core.orchestra_agents.backends.opencode.main"),
                manifest_text,
            )
            self.assertFalse((output_dir / "agent_runtime").exists())
            self.assertTrue((output_dir / "system_prompt.md").exists())

    def _assert_generated_configs(self, output_dir: Path) -> None:
        self.assertTrue((output_dir / ".agent-mux" / "config.toml").exists())
        self.assertTrue((output_dir / ".codex" / "config.toml").exists())
