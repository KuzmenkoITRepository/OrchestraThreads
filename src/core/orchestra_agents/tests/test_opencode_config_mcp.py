from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.orchestra_agents.backends.opencode.config_mcp import build_mcp_block


class OpencodeMCPConfigTests(unittest.TestCase):
    def test_build_mcp_block_multi_servers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            payload = build_mcp_block(
                config_dir=config_dir,
                cfg={
                    "mcp_servers": [
                        {
                            "name": "orchestra_threads",
                            "command": "python",
                            "args": ["-m", "core.orchestra_thread.mcp_server"],
                            "env": {
                                "ORCHESTRA_THREADS_URL": "http://orchestra-threads:8788",
                                "PYTHONPATH": "/workspace/src",
                            },
                        },
                        {
                            "name": "task_registry",
                            "command": "python",
                            "args": ["-m", "core.task_registry.mcp_server"],
                            "env": {
                                "TASK_REGISTRY_DATABASE_URL": "postgresql://example",
                                "PYTHONPATH": "/workspace/src",
                            },
                        },
                    ]
                },
                agent_slug="whiner",
                working_dir="/workspace/agents/whiner",
            )

        self.assertIn("orchestra_threads", payload)
        self.assertIn("task_registry", payload)
        self.assertEqual(payload["orchestra_threads"]["type"], "local")
        self.assertEqual(payload["task_registry"]["type"], "local")
        self.assertEqual(
            payload["task_registry"]["command"],
            ["python", "-m", "core.task_registry.mcp_server"],
        )
        self.assertIn("environment", payload["task_registry"])
