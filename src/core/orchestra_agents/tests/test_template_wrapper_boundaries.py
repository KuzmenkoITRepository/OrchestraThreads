from __future__ import annotations

import importlib
import unittest
from typing import Any
from unittest.mock import patch

_AGENT_TEMPLATE_MODULE = "core.orchestra_agents.templates.agent.agent_runtime"
_AGENT_MUX_TEMPLATE_MODULE = "core.orchestra_agents.templates.agent_mux.agent_runtime"
_OPENCODE_TEMPLATE_MODULE = "core.orchestra_agents.templates.opencode.agent_runtime"


def _load(module_path: str) -> Any:
    return importlib.import_module(module_path)


def _symbol(module_path: str, name: str) -> Any:
    return getattr(_load(module_path), name)


def _assert_same(case: unittest.TestCase, pairs: tuple[tuple[object, object], ...]) -> None:
    for left, right in pairs:
        case.assertIs(left, right)


class TemplateWrapperBoundaryTests(unittest.TestCase):
    def test_agent_backend_reexport(self) -> None:
        _assert_same(
            self,
            (
                (
                    _symbol(f"{_AGENT_TEMPLATE_MODULE}.backend", "TemplateBackend"),
                    _symbol("core.orchestra_agents.backends.example.backend", "TemplateBackend"),
                ),
            ),
        )

    def test_agent_main_reexport(self) -> None:
        _assert_same(
            self,
            (
                (
                    _symbol(f"{_AGENT_TEMPLATE_MODULE}.main", "main"),
                    _symbol("core.orchestra_agents.backends.example.main", "main"),
                ),
            ),
        )

    def test_agent_mux_shims_match_symbols(self) -> None:
        _assert_same(
            self,
            (
                (
                    _symbol(f"{_AGENT_MUX_TEMPLATE_MODULE}", "AgentMuxBackend"),
                    _symbol("core.orchestra_agents.backends.agent_mux.backend", "AgentMuxBackend"),
                ),
                (
                    _symbol(f"{_AGENT_MUX_TEMPLATE_MODULE}.backend", "AgentMuxBackend"),
                    _symbol("core.orchestra_agents.backends.agent_mux.backend", "AgentMuxBackend"),
                ),
                (
                    _symbol(f"{_AGENT_MUX_TEMPLATE_MODULE}.state", "AgentMuxRuntimeState"),
                    _symbol(
                        "core.orchestra_agents.backends.agent_mux.internal.state_store",
                        "AgentMuxRuntimeState",
                    ),
                ),
                (
                    _symbol(f"{_AGENT_MUX_TEMPLATE_MODULE}.state", "QueueEntry"),
                    _symbol(
                        "core.orchestra_agents.backends.agent_mux.internal.queue_mutations",
                        "QueueEntry",
                    ),
                ),
                (
                    _symbol(f"{_AGENT_MUX_TEMPLATE_MODULE}.dispatch", "AgentMuxDispatchSpec"),
                    _symbol(
                        "core.orchestra_agents.backends.agent_mux.dispatch_engine",
                        "AgentMuxDispatchSpec",
                    ),
                ),
                (
                    _symbol(f"{_AGENT_MUX_TEMPLATE_MODULE}.dispatch", "build_agent_mux_command"),
                    _symbol(
                        "core.orchestra_agents.backends.agent_mux.dispatch_engine",
                        "build_agent_mux_command",
                    ),
                ),
                (
                    _symbol(f"{_AGENT_MUX_TEMPLATE_MODULE}.dispatch", "parse_agent_mux_result"),
                    _symbol(
                        "core.orchestra_agents.backends.agent_mux.dispatch_engine",
                        "parse_agent_mux_result",
                    ),
                ),
                (
                    _symbol(
                        f"{_AGENT_MUX_TEMPLATE_MODULE}.dispatch",
                        "write_runtime_codex_config",
                    ),
                    _symbol(
                        "core.orchestra_agents.backends.agent_mux.codex_config",
                        "write_runtime_codex_config",
                    ),
                ),
                (
                    _symbol(
                        f"{_AGENT_MUX_TEMPLATE_MODULE}.prompting", "build_compact_wakeup_block"
                    ),
                    _symbol(
                        "core.orchestra_agents.backends.agent_mux.internal.prompt_builder",
                        "build_compact_wakeup_block",
                    ),
                ),
                (
                    _symbol(
                        f"{_AGENT_MUX_TEMPLATE_MODULE}.prompting", "build_context_memory_block"
                    ),
                    _symbol(
                        "core.orchestra_agents.backends.agent_mux.internal.context_memory",
                        "build_context_memory_block",
                    ),
                ),
            ),
        )

    def test_agent_mux_main_delegates(self) -> None:
        template_main_module = f"{_AGENT_MUX_TEMPLATE_MODULE}.main"
        template_main = _load(template_main_module)
        with patch(f"{template_main_module}.run_backend") as run_backend:
            template_main.main()
            run_backend.assert_called_once_with(
                backend_factory=_symbol(
                    "core.orchestra_agents.backends.agent_mux.backend",
                    "AgentMuxBackend",
                ),
                working_dir_fallback="/workspace/agents/__AGENT_SLUG__",
                agent_slug_fallback="__AGENT_SLUG__",
                backend_type_fallback="__BACKEND_TYPE__",
            )

    def test_opencode_shims_match_symbols(self) -> None:
        _assert_same(
            self,
            (
                (
                    _symbol(f"{_OPENCODE_TEMPLATE_MODULE}", "OpencodeOmoBackend"),
                    _symbol(
                        "core.orchestra_agents.backends.opencode.backend", "OpencodeOmoBackend"
                    ),
                ),
                (
                    _symbol(f"{_OPENCODE_TEMPLATE_MODULE}.backend", "OpencodeOmoBackend"),
                    _symbol(
                        "core.orchestra_agents.backends.opencode.backend", "OpencodeOmoBackend"
                    ),
                ),
                (
                    _symbol(f"{_OPENCODE_TEMPLATE_MODULE}.backend", "_DEFAULT_DISPATCH_TIMEOUT"),
                    _symbol(
                        "core.orchestra_agents.backends.opencode.backend",
                        "_DEFAULT_DISPATCH_TIMEOUT",
                    ),
                ),
                (
                    _symbol(f"{_OPENCODE_TEMPLATE_MODULE}.backend", "_DEFAULT_READY_TIMEOUT"),
                    _symbol(
                        "core.orchestra_agents.backends.opencode.backend",
                        "_DEFAULT_READY_TIMEOUT",
                    ),
                ),
                (
                    _symbol(f"{_OPENCODE_TEMPLATE_MODULE}.backend", "_DEFAULT_SERVE_PORT"),
                    _symbol(
                        "core.orchestra_agents.backends.opencode.backend",
                        "_DEFAULT_SERVE_PORT",
                    ),
                ),
                (
                    _symbol(f"{_OPENCODE_TEMPLATE_MODULE}.backend", "_SEEN_IDS_LIMIT"),
                    _symbol("core.orchestra_agents.backends.opencode.backend", "_SEEN_IDS_LIMIT"),
                ),
                (
                    _symbol(f"{_OPENCODE_TEMPLATE_MODULE}.backend", "_optional_str"),
                    _symbol("core.orchestra_agents.backends.opencode.backend", "_optional_str"),
                ),
                (
                    _symbol(f"{_OPENCODE_TEMPLATE_MODULE}.backend", "_to_float"),
                    _symbol("core.orchestra_agents.backends.opencode.backend", "_to_float"),
                ),
                (
                    _symbol(f"{_OPENCODE_TEMPLATE_MODULE}.backend", "_to_int"),
                    _symbol("core.orchestra_agents.backends.opencode.backend", "_to_int"),
                ),
                (
                    _symbol(f"{_OPENCODE_TEMPLATE_MODULE}.config_provider", "_CONTEXT_LIMIT"),
                    _symbol(
                        "core.orchestra_agents.backends.opencode.config_provider", "_CONTEXT_LIMIT"
                    ),
                ),
                (
                    _symbol(
                        f"{_OPENCODE_TEMPLATE_MODULE}.config_provider",
                        "_DEFAULT_OMNIROUTE_URL",
                    ),
                    _symbol(
                        "core.orchestra_agents.backends.opencode.config_provider",
                        "_DEFAULT_OMNIROUTE_URL",
                    ),
                ),
                (
                    _symbol(f"{_OPENCODE_TEMPLATE_MODULE}.config_provider", "_OUTPUT_LIMIT"),
                    _symbol(
                        "core.orchestra_agents.backends.opencode.config_provider", "_OUTPUT_LIMIT"
                    ),
                ),
                (
                    _symbol(f"{_OPENCODE_TEMPLATE_MODULE}.config_provider", "ProviderModel"),
                    _symbol(
                        "core.orchestra_agents.backends.opencode.config_provider", "ProviderModel"
                    ),
                ),
                (
                    _symbol(f"{_OPENCODE_TEMPLATE_MODULE}.config_provider", "ProviderModelMap"),
                    _symbol(
                        "core.orchestra_agents.backends.opencode.config_provider",
                        "ProviderModelMap",
                    ),
                ),
                (
                    _symbol(f"{_OPENCODE_TEMPLATE_MODULE}.config_provider", "_extend_names"),
                    _symbol(
                        "core.orchestra_agents.backends.opencode.config_provider",
                        "_extend_names",
                    ),
                ),
                (
                    _symbol(f"{_OPENCODE_TEMPLATE_MODULE}.config_provider", "_model_entry"),
                    _symbol(
                        "core.orchestra_agents.backends.opencode.config_provider",
                        "_model_entry",
                    ),
                ),
                (
                    _symbol(f"{_OPENCODE_TEMPLATE_MODULE}.config_provider", "_model_map"),
                    _symbol(
                        "core.orchestra_agents.backends.opencode.config_provider", "_model_map"
                    ),
                ),
                (
                    _symbol(f"{_OPENCODE_TEMPLATE_MODULE}.config_provider", "_model_name"),
                    _symbol(
                        "core.orchestra_agents.backends.opencode.config_provider", "_model_name"
                    ),
                ),
                (
                    _symbol(f"{_OPENCODE_TEMPLATE_MODULE}.config_provider", "_provider_models"),
                    _symbol(
                        "core.orchestra_agents.backends.opencode.config_provider",
                        "_provider_models",
                    ),
                ),
                (
                    _symbol(f"{_OPENCODE_TEMPLATE_MODULE}.config_provider", "_provider_options"),
                    _symbol(
                        "core.orchestra_agents.backends.opencode.config_provider",
                        "_provider_options",
                    ),
                ),
                (
                    _symbol(f"{_OPENCODE_TEMPLATE_MODULE}.config_provider", "build_provider_entry"),
                    _symbol(
                        "core.orchestra_agents.backends.opencode.config_provider",
                        "build_provider_entry",
                    ),
                ),
            ),
        )

    def test_opencode_main_reexport(self) -> None:
        _assert_same(
            self,
            (
                (
                    _symbol(f"{_OPENCODE_TEMPLATE_MODULE}.main", "main"),
                    _symbol("core.orchestra_agents.backends.opencode.main", "main"),
                ),
            ),
        )
