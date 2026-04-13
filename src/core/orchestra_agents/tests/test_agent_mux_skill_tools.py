from __future__ import annotations

import importlib
import sys
import tempfile
import types
import unittest
from typing import Any, Protocol, cast


def _install_test_stubs() -> None:
    sys.modules.setdefault("yaml", types.ModuleType("yaml"))

    asyncpg_stub: Any = types.ModuleType("asyncpg")
    asyncpg_stub.Pool = object
    asyncpg_stub.Connection = object
    asyncpg_stub.Record = dict
    sys.modules.setdefault("asyncpg", asyncpg_stub)


_install_test_stubs()

backend_module = importlib.import_module(
    "core.orchestra_agents.backends.agent_mux.backend",
)


class _AgentMuxBackendProtocol(Protocol):
    _openai_tools: list[dict[str, Any]]

    def list_skills(self) -> str: ...

    def get_skill_instructions(self, skill_id: str) -> str | None: ...


AgentMuxBackendFactory = cast(Any, backend_module.AgentMuxBackend)


class AgentMuxSkillToolsTests(unittest.TestCase):
    def test_skill_tools_are_callable(self) -> None:
        backend = self._build_backend()

        menu = backend.list_skills()
        instructions = backend.get_skill_instructions("memory")

        self.assertIn("<AVAILABLE_SKILLS>", menu)
        self.assertIn("Memory", menu)
        self.assertIsNotNone(instructions)
        self.assertIn("Store and retrieve persistent memory entries", instructions or "")

    def test_skill_tools_are_exposed(self) -> None:
        backend = self._build_backend()

        tool_names = [tool["function"]["name"] for tool in backend._openai_tools]

        self.assertIn("list_skills", tool_names)
        self.assertIn("get_skill_instructions", tool_names)

    def _build_backend(self) -> _AgentMuxBackendProtocol:
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        return cast(
            _AgentMuxBackendProtocol,
            AgentMuxBackendFactory(
                agent_slug="agent",
                backend_type="agent_mux",
                working_dir=tempdir.name,
                config={},
                system_prompt="",
            ),
        )
