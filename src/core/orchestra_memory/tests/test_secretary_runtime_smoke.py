from __future__ import annotations

import unittest
from pathlib import Path

from core.orchestra_agents.manifest import AgentManifest
from core.orchestra_memory.mcp.server import orchestra_memory_tool_definitions

_SECRETARY_MANIFEST = Path("agents/secretary/manifest.yaml")
_EXPECTED_MEMORY_URL = "http://orchestra-memory:8793"
_EXPECTED_MEMORY_MCP = {
    "name": "orchestra_memory",
    "module": "core.orchestra_memory.mcp.server",
    "class": "OrchestraMemoryMCPServer",
    "schema_fn": "orchestra_memory_tool_definitions",
}
_EXPECTED_MEMORY_TOOL_NAMES = {
    "memory_remember",
    "memory_search",
    "memory_delete",
    "memory_clear",
    "memory_list_rooms",
    "memory_list_categories",
}


class SecretaryRuntimeSmokeTests(unittest.IsolatedAsyncioTestCase):
    async def test_secretary_manifest_has_memory_mcp(self) -> None:
        manifest = AgentManifest.from_file(_SECRETARY_MANIFEST)
        backend_config = manifest.backend.config
        mcp_servers = backend_config["mcp_servers"]

        self.assertIsInstance(mcp_servers, list)
        self.assertIn(_EXPECTED_MEMORY_MCP, mcp_servers)

    async def test_secretary_memory_url_configured(self) -> None:
        manifest = AgentManifest.from_file(_SECRETARY_MANIFEST)
        runtime_env = manifest.runtime.env

        self.assertEqual(runtime_env["ORCHESTRA_MEMORY_URL"], _EXPECTED_MEMORY_URL)

    async def test_secretary_can_start(self) -> None:
        manifest = AgentManifest.from_file(_SECRETARY_MANIFEST)

        self.assertTrue(manifest.is_active)
        self.assertTrue(manifest.auto_start)
        self.assertEqual(manifest.backend.type, "sgr_minimax")
        self.assertEqual(
            list(manifest.runtime.command),
            ["python", "-m", "core.orchestra_agents.backends.sgr.main"],
        )

    async def test_orchestra_memory_tool_definitions_are_complete(self) -> None:
        tool_names = {tool["name"] for tool in orchestra_memory_tool_definitions()}

        self.assertEqual(tool_names, _EXPECTED_MEMORY_TOOL_NAMES)
