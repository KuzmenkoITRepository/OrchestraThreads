from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast

from core.orchestra_agents.backends.opencode.config_mcp import build_mcp_block
from core.orchestra_agents.backends.opencode.opencode_config import (
    write_opencode_config,
)


class OpencodeMcpConfigTests(unittest.TestCase):
    def test_mcp_block_renders_servers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / "runtime_state" / "opencode" / "config"
            payload = build_mcp_block(
                config_dir=config_dir,
                cfg={"mcp_servers": _mcp_servers_payload()},
                agent_slug="secretary",
                working_dir="/workspace/agents/secretary",
            )

        self.assertEqual(sorted(payload.keys()), ["orchestra_memory", "orchestra_threads"])
        self.assertEqual(
            payload["orchestra_memory"]["command"],
            ["python", "-m", "core.orchestra_memory.mcp_server"],
        )
        self.assertEqual(
            payload["orchestra_memory"]["environment"]["ORCHESTRA_MEMORY_URL"],
            "http://orchestra-memory:8793",
        )
        self.assertEqual(
            payload["orchestra_threads"]["environment"]["ORCHESTRA_THREADS_AGENT_SLUG"],
            "secretary",
        )

    def test_config_includes_all_mcp(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = write_opencode_config(
                config_dir=Path(tmpdir) / "runtime_state" / "opencode" / "config",
                backend_config={
                    "model": "gpt-5.4-mini",
                    "mcp_servers": _mcp_servers_payload(),
                },
                agent_slug="secretary",
                working_dir="/workspace/agents/secretary",
            )
            payload = json.loads(config_path.read_text(encoding="utf-8"))

        mcp_block = cast(dict[str, Any], payload["mcp"])
        self.assertIn("orchestra_threads", mcp_block)
        self.assertIn("orchestra_memory", mcp_block)
        self.assertEqual(mcp_block["orchestra_memory"]["type"], "local")


def _mcp_servers_payload() -> list[dict[str, Any]]:
    return [
        {
            "name": "orchestra_threads",
            "command": "python",
            "args": ["-m", "core.orchestra_thread.mcp_server"],
            "env": {"PYTHONPATH": "/workspace/src"},
        },
        {
            "name": "orchestra_memory",
            "command": "python",
            "args": ["-m", "core.orchestra_memory.mcp_server"],
            "env": {
                "PYTHONPATH": "/workspace/src",
                "ORCHESTRA_MEMORY_URL": "http://orchestra-memory:8793",
            },
        },
    ]
