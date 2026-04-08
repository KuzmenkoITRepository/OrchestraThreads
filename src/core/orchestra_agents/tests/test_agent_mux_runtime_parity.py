from __future__ import annotations

import importlib
import unittest
from typing import Any
from unittest.mock import patch

_SHARED_RUNTIME_MODULE = "core.orchestra_agents.agent_mux_runtime"
_TEMPLATE_STATE_MODULE = "core.orchestra_agents.templates.agent_mux.agent_runtime.state"
_TEMPLATE_DISPATCH_MODULE = "core.orchestra_agents.templates.agent_mux.agent_runtime.dispatch"
_TEMPLATE_PROMPTING_MODULE = "core.orchestra_agents.templates.agent_mux.agent_runtime.prompting"
_EXAMPLE_STATE_MODULE = "agents.orchestra.agent_runtime.state"
_EXAMPLE_DISPATCH_MODULE = "agents.orchestra.agent_runtime.dispatch"
_EXAMPLE_PROMPTING_MODULE = "agents.orchestra.agent_runtime.prompting"
_STATE_NAME = "AgentMuxRuntimeState"
_QUEUE_ENTRY_NAME = "QueueEntry"
_DISPATCH_SPEC_NAME = "AgentMuxDispatchSpec"
_BUILD_COMMAND_NAME = "build_agent_mux_command"
_PARSE_RESULT_NAME = "parse_agent_mux_result"
_WRITE_CONFIG_NAME = "write_runtime_codex_config"
_WAKEUP_BLOCK_NAME = "build_compact_wakeup_block"
_CONTEXT_BLOCK_NAME = "build_context_memory_block"


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
                        _TEMPLATE_STATE_MODULE,
                        _STATE_NAME,
                    ),
                    _symbol(_SHARED_RUNTIME_MODULE, _STATE_NAME),
                ),
                (
                    _symbol(
                        _TEMPLATE_STATE_MODULE,
                        _QUEUE_ENTRY_NAME,
                    ),
                    _symbol(_SHARED_RUNTIME_MODULE, _QUEUE_ENTRY_NAME),
                ),
                (
                    _symbol(
                        _TEMPLATE_DISPATCH_MODULE,
                        _DISPATCH_SPEC_NAME,
                    ),
                    _symbol(_SHARED_RUNTIME_MODULE, _DISPATCH_SPEC_NAME),
                ),
                (
                    _symbol(
                        _TEMPLATE_DISPATCH_MODULE,
                        _BUILD_COMMAND_NAME,
                    ),
                    _symbol(_SHARED_RUNTIME_MODULE, _BUILD_COMMAND_NAME),
                ),
                (
                    _symbol(
                        _TEMPLATE_DISPATCH_MODULE,
                        _PARSE_RESULT_NAME,
                    ),
                    _symbol(_SHARED_RUNTIME_MODULE, _PARSE_RESULT_NAME),
                ),
                (
                    _symbol(
                        _TEMPLATE_DISPATCH_MODULE,
                        _WRITE_CONFIG_NAME,
                    ),
                    _symbol(_SHARED_RUNTIME_MODULE, _WRITE_CONFIG_NAME),
                ),
                (
                    _symbol(
                        _TEMPLATE_PROMPTING_MODULE,
                        _WAKEUP_BLOCK_NAME,
                    ),
                    _symbol(_SHARED_RUNTIME_MODULE, _WAKEUP_BLOCK_NAME),
                ),
                (
                    _symbol(
                        _TEMPLATE_PROMPTING_MODULE,
                        _CONTEXT_BLOCK_NAME,
                    ),
                    _symbol(_SHARED_RUNTIME_MODULE, _CONTEXT_BLOCK_NAME),
                ),
            ),
        )

    def test_example_exports_match_shared(self) -> None:
        _assert_same(
            self,
            (
                (
                    _symbol(_EXAMPLE_STATE_MODULE, _STATE_NAME),
                    _symbol(_SHARED_RUNTIME_MODULE, _STATE_NAME),
                ),
                (
                    _symbol(_EXAMPLE_STATE_MODULE, _QUEUE_ENTRY_NAME),
                    _symbol(_SHARED_RUNTIME_MODULE, _QUEUE_ENTRY_NAME),
                ),
                (
                    _symbol(_EXAMPLE_DISPATCH_MODULE, _DISPATCH_SPEC_NAME),
                    _symbol(_SHARED_RUNTIME_MODULE, _DISPATCH_SPEC_NAME),
                ),
                (
                    _symbol(_EXAMPLE_DISPATCH_MODULE, _BUILD_COMMAND_NAME),
                    _symbol(_SHARED_RUNTIME_MODULE, _BUILD_COMMAND_NAME),
                ),
                (
                    _symbol(_EXAMPLE_DISPATCH_MODULE, _PARSE_RESULT_NAME),
                    _symbol(_SHARED_RUNTIME_MODULE, _PARSE_RESULT_NAME),
                ),
                (
                    _symbol(_EXAMPLE_DISPATCH_MODULE, _WRITE_CONFIG_NAME),
                    _symbol(_SHARED_RUNTIME_MODULE, _WRITE_CONFIG_NAME),
                ),
                (
                    _symbol(_EXAMPLE_PROMPTING_MODULE, _WAKEUP_BLOCK_NAME),
                    _symbol(_SHARED_RUNTIME_MODULE, _WAKEUP_BLOCK_NAME),
                ),
                (
                    _symbol(_EXAMPLE_PROMPTING_MODULE, _CONTEXT_BLOCK_NAME),
                    _symbol(_SHARED_RUNTIME_MODULE, _CONTEXT_BLOCK_NAME),
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
