from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, _patch, patch

from core.orchestra_agents.templates.opencode.agent_runtime.backend import (
    OpencodeOmoBackend,
)


class OpencodeMemoryE2ETests(unittest.IsolatedAsyncioTestCase):
    async def test_memory_mcp_is_written_during_backend_startup(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            working_dir = str(Path(tmpdir) / "agent")
            config = _backend_config()
            backend = OpencodeOmoBackend(
                agent_slug="secretary",
                backend_type="opencode_omo",
                working_dir=working_dir,
                http_endpoint="http://secretary:8787",
                config=config,
            )

            with _patched_opencode_runtime():
                await backend.on_start()
                config_path = backend._paths.config_dir / "opencode.json"  # noqa: SLF001
                payload = _read_opencode_payload(config_path)
                await backend.on_shutdown()

        mcp_block = cast(dict[str, Any], payload["mcp"])
        memory_block = cast(dict[str, Any], mcp_block["orchestra_memory"])
        memory_env = cast(dict[str, str], memory_block["environment"])
        self.assertIn("orchestra_memory", mcp_block)
        self.assertEqual(
            memory_block["command"],
            ["python", "-m", "core.orchestra_memory.mcp_server"],
        )
        self.assertEqual(
            memory_env["ORCHESTRA_MEMORY_URL"],
            "http://orchestra-memory:8793",
        )
        self.assertEqual(
            memory_env["ORCHESTRA_AGENT_SLUG"],
            "secretary",
        )


def _backend_config() -> dict[str, object]:
    return {
        "model": "gpt-5.4-mini",
        "opencode_serve_port": 4096,
        "dispatch_timeout_seconds": 120,
        "startup_timeout_seconds": 20,
        "mcp_servers": [
            {
                "name": "orchestra_threads",
                "command": "python",
                "args": ["-m", "core.orchestra_thread.mcp_server"],
                "env": {
                    "PYTHONPATH": "/workspace/src:/workspace/agents/secretary",
                    "ORCHESTRA_THREADS_URL": "http://orchestra-threads:8788",
                },
            },
            {
                "name": "orchestra_memory",
                "command": "python",
                "args": ["-m", "core.orchestra_memory.mcp_server"],
                "env": {
                    "PYTHONPATH": "/workspace/src:/workspace/agents/secretary",
                    "ORCHESTRA_MEMORY_URL": "http://orchestra-memory:8793",
                    "ORCHESTRA_AGENT_SLUG": "secretary",
                },
            },
        ],
    }


def _patched_opencode_runtime() -> _PatchedRuntime:
    return _PatchedRuntime()


class _PatchedRuntime:
    _patchers: list[_patch[Any]]

    def __enter__(self) -> None:
        self._patchers = [
            patch(
                "core.orchestra_agents.templates.opencode.agent_runtime.opencode_process.OpencodeProcess.start",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "core.orchestra_agents.templates.opencode.agent_runtime.opencode_process.OpencodeProcess.wait_ready",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "core.orchestra_agents.templates.opencode.agent_runtime.opencode_process.OpencodeProcess.stop",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "core.orchestra_agents.templates.opencode.agent_runtime.opencode_client.OpencodeClient",
                new=_FakeOpencodeClient,
            ),
            patch(
                "core.orchestra_agents.templates.opencode.agent_runtime.backend_registration.register_with_threads",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "core.orchestra_agents.templates.opencode.agent_runtime.backend_registration.stop_registration",
                new=AsyncMock(return_value=None),
            ),
        ]
        for patcher in self._patchers:
            patcher.start()

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        for patcher in reversed(self._patchers):
            patcher.stop()


def _read_opencode_payload(config_path: Path) -> dict[str, object]:
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


class _FakeOpencodeClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.closed = False

    async def list_sessions(self) -> list[dict[str, object]]:
        return []

    async def close(self) -> None:
        self.closed = True
