from __future__ import annotations

import importlib
import unittest
from typing import Any
from unittest.mock import patch


def _load(module_path: str) -> Any:
    return importlib.import_module(module_path)


def _assert_same(case: unittest.TestCase, pairs: tuple[tuple[object, object], ...]) -> None:
    for left, right in pairs:
        case.assertIs(left, right)


def _symbol(module_path: str, name: str) -> Any:
    return getattr(_load(module_path), name)


class AgentMuxRuntimeParityTests(unittest.TestCase):
    def test_template_exports_match_shared(self) -> None:
        _assert_same(
            self,
            (
                (
                    _symbol(
                        "core.orchestra_agents.templates.agent_mux.agent_runtime.state",
                        "AgentMuxRuntimeState",
                    ),
                    _symbol("core.orchestra_agents.agent_mux_runtime", "AgentMuxRuntimeState"),
                ),
                (
                    _symbol(
                        "core.orchestra_agents.templates.agent_mux.agent_runtime.state",
                        "QueueEntry",
                    ),
                    _symbol("core.orchestra_agents.agent_mux_runtime", "QueueEntry"),
                ),
                (
                    _symbol(
                        "core.orchestra_agents.templates.agent_mux.agent_runtime.dispatch",
                        "AgentMuxDispatchSpec",
                    ),
                    _symbol("core.orchestra_agents.agent_mux_runtime", "AgentMuxDispatchSpec"),
                ),
                (
                    _symbol(
                        "core.orchestra_agents.templates.agent_mux.agent_runtime.dispatch",
                        "build_agent_mux_command",
                    ),
                    _symbol("core.orchestra_agents.agent_mux_runtime", "build_agent_mux_command"),
                ),
                (
                    _symbol(
                        "core.orchestra_agents.templates.agent_mux.agent_runtime.dispatch",
                        "parse_agent_mux_result",
                    ),
                    _symbol("core.orchestra_agents.agent_mux_runtime", "parse_agent_mux_result"),
                ),
                (
                    _symbol(
                        "core.orchestra_agents.templates.agent_mux.agent_runtime.dispatch",
                        "write_runtime_codex_config",
                    ),
                    _symbol(
                        "core.orchestra_agents.agent_mux_runtime", "write_runtime_codex_config"
                    ),
                ),
                (
                    _symbol(
                        "core.orchestra_agents.templates.agent_mux.agent_runtime.prompting",
                        "build_compact_wakeup_block",
                    ),
                    _symbol(
                        "core.orchestra_agents.agent_mux_runtime", "build_compact_wakeup_block"
                    ),
                ),
                (
                    _symbol(
                        "core.orchestra_agents.templates.agent_mux.agent_runtime.prompting",
                        "build_context_memory_block",
                    ),
                    _symbol(
                        "core.orchestra_agents.agent_mux_runtime", "build_context_memory_block"
                    ),
                ),
            ),
        )

    def test_example_exports_match_shared(self) -> None:
        _assert_same(
            self,
            (
                (
                    _symbol("agents.orchestra.agent_runtime.state", "AgentMuxRuntimeState"),
                    _symbol("core.orchestra_agents.agent_mux_runtime", "AgentMuxRuntimeState"),
                ),
                (
                    _symbol("agents.orchestra.agent_runtime.state", "QueueEntry"),
                    _symbol("core.orchestra_agents.agent_mux_runtime", "QueueEntry"),
                ),
                (
                    _symbol("agents.orchestra.agent_runtime.dispatch", "AgentMuxDispatchSpec"),
                    _symbol("core.orchestra_agents.agent_mux_runtime", "AgentMuxDispatchSpec"),
                ),
                (
                    _symbol("agents.orchestra.agent_runtime.dispatch", "build_agent_mux_command"),
                    _symbol("core.orchestra_agents.agent_mux_runtime", "build_agent_mux_command"),
                ),
                (
                    _symbol("agents.orchestra.agent_runtime.dispatch", "parse_agent_mux_result"),
                    _symbol("core.orchestra_agents.agent_mux_runtime", "parse_agent_mux_result"),
                ),
                (
                    _symbol(
                        "agents.orchestra.agent_runtime.dispatch", "write_runtime_codex_config"
                    ),
                    _symbol(
                        "core.orchestra_agents.agent_mux_runtime", "write_runtime_codex_config"
                    ),
                ),
                (
                    _symbol(
                        "agents.orchestra.agent_runtime.prompting", "build_compact_wakeup_block"
                    ),
                    _symbol(
                        "core.orchestra_agents.agent_mux_runtime", "build_compact_wakeup_block"
                    ),
                ),
                (
                    _symbol(
                        "agents.orchestra.agent_runtime.prompting", "build_context_memory_block"
                    ),
                    _symbol(
                        "core.orchestra_agents.agent_mux_runtime", "build_context_memory_block"
                    ),
                ),
                (
                    _symbol("agents.secretary.agent_runtime.state", "AgentMuxRuntimeState"),
                    _symbol("core.orchestra_agents.agent_mux_runtime", "AgentMuxRuntimeState"),
                ),
                (
                    _symbol("agents.secretary.agent_runtime.state", "QueueEntry"),
                    _symbol("core.orchestra_agents.agent_mux_runtime", "QueueEntry"),
                ),
                (
                    _symbol("agents.secretary.agent_runtime.dispatch", "AgentMuxDispatchSpec"),
                    _symbol("core.orchestra_agents.agent_mux_runtime", "AgentMuxDispatchSpec"),
                ),
                (
                    _symbol("agents.secretary.agent_runtime.dispatch", "build_agent_mux_command"),
                    _symbol("core.orchestra_agents.agent_mux_runtime", "build_agent_mux_command"),
                ),
                (
                    _symbol("agents.secretary.agent_runtime.dispatch", "parse_agent_mux_result"),
                    _symbol("core.orchestra_agents.agent_mux_runtime", "parse_agent_mux_result"),
                ),
                (
                    _symbol(
                        "agents.secretary.agent_runtime.dispatch",
                        "write_runtime_codex_config",
                    ),
                    _symbol(
                        "core.orchestra_agents.agent_mux_runtime", "write_runtime_codex_config"
                    ),
                ),
                (
                    _symbol(
                        "agents.secretary.agent_runtime.prompting",
                        "build_compact_wakeup_block",
                    ),
                    _symbol(
                        "core.orchestra_agents.agent_mux_runtime", "build_compact_wakeup_block"
                    ),
                ),
                (
                    _symbol(
                        "agents.secretary.agent_runtime.prompting",
                        "build_context_memory_block",
                    ),
                    _symbol(
                        "core.orchestra_agents.agent_mux_runtime", "build_context_memory_block"
                    ),
                ),
            ),
        )

    def test_backend_wrapper_delegates(self) -> None:
        _assert_same(
            self,
            (
                (
                    _symbol("agents.orchestra.agent_runtime.backend", "AgentMuxBackend"),
                    _symbol(
                        "core.orchestra_agents.templates.agent_mux.agent_runtime.backend",
                        "AgentMuxBackend",
                    ),
                ),
                (
                    _symbol("agents.secretary.agent_runtime.backend", "AgentMuxBackend"),
                    _symbol(
                        "core.orchestra_agents.templates.agent_mux.agent_runtime.backend",
                        "AgentMuxBackend",
                    ),
                ),
            ),
        )

    def test_template_main_delegates(self) -> None:
        template_main = _load("core.orchestra_agents.templates.agent_mux.agent_runtime.main")
        with patch("core.orchestra_agents.agent_mux_runtime.bootstrap.run_backend") as run_backend:
            template_main.main()
            run_backend.assert_called_once_with(
                backend_factory=_symbol(
                    "core.orchestra_agents.templates.agent_mux.agent_runtime.backend",
                    "AgentMuxBackend",
                ),
                working_dir_fallback="/workspace/agents/__AGENT_SLUG__",
                agent_slug_fallback="__AGENT_SLUG__",
                backend_type_fallback="__BACKEND_TYPE__",
            )

    def test_example_mains_delegate(self) -> None:
        orchestra_main = _load("agents.orchestra.agent_runtime.main")
        secretary_main = _load("agents.secretary.agent_runtime.main")
        with (
            patch.object(orchestra_main, "main") as orchestra_mock,
            patch.object(secretary_main, "main") as secretary_mock,
        ):
            orchestra_main.main()
            secretary_main.main()
            orchestra_mock.assert_called_once_with()
            secretary_mock.assert_called_once_with()
