from __future__ import annotations

import importlib
import io
import unittest
from unittest.mock import Mock, patch

from core.orchestra_thread import agent_cli as agent_cli_module
from core.orchestra_thread.agent_cli import ManualAgentCLI

agent_cli_app = importlib.import_module("core.orchestra_thread.agent_cli.app")

_MANUAL_AGENT_METHODS = (
    "_dispatch_command",
    "_handle_event",
    "_handle_stop",
    "_handle_health",
    "start",
    "stop",
)


def _assert_has_attr(case: unittest.TestCase, obj: object, attr_name: str) -> None:
    case.assertTrue(hasattr(obj, attr_name))


def _help_output() -> tuple[int, str]:
    parser = agent_cli_module._build_arg_parser()
    capture = _HelpCapture()
    return capture.parse(parser)


class _HelpCapture(unittest.TestCase):
    def parse(self, parser: Mock) -> tuple[int, str]:
        with patch("sys.stdout", new_callable=io.StringIO) as output:
            return self._parse_with_output(parser, output)

    def _parse_with_output(self, parser: Mock, output: io.StringIO) -> tuple[int, str]:
        try:
            parser.parse_args(["--help"])
        except SystemExit as exit_error:
            return self._exit_code(exit_error.code), output.getvalue()
        raise AssertionError("help flag should exit")

    @staticmethod
    def _exit_code(code: object) -> int:
        if not isinstance(code, int):
            raise AssertionError("Expected integer help exit code")
        return code


class ManualAgentCLICompatibilityTests(unittest.TestCase):
    def test_cli_import_path_exports_class(self) -> None:
        module = importlib.import_module("core.orchestra_thread.agent_cli")

        self.assertIs(module.ManualAgentCLI, ManualAgentCLI)

    def test_required_methods_stay_available(self) -> None:
        for attr_name in _MANUAL_AGENT_METHODS:
            with self.subTest(attr_name=attr_name):
                _assert_has_attr(self, ManualAgentCLI, attr_name)

    def test_runtime_exports_stay_available(self) -> None:
        runtime = importlib.import_module("core.orchestra_thread.service.runtime")

        _assert_has_attr(self, runtime, "OrchestraThreadsService")
        _assert_has_attr(self, runtime, "build_app")

    def test_cli_help_path_stays_available(self) -> None:
        exit_code, output = _help_output()

        self.assertEqual(exit_code, 0)
        self.assertIn("Manual CLI agent for OrchestraThreads", output)
        self.assertIn("--slug", output)

    def test_main_uses_parsed_args(self) -> None:
        runner = _MainRunner()

        runner.run_main()

        runner.assert_called_once_with()


class _MainRunner:
    def __init__(self) -> None:
        self.parsed = object()
        self.entrypoint = object()
        self.main_async = Mock(return_value=self.entrypoint)
        self.run_call = Mock()
        self.parser = Mock()

    def run_main(self) -> None:
        with patch.object(agent_cli_app, "_build_arg_parser") as parser_factory:
            self.parser = parser_factory.return_value
            self.parser.parse_args.return_value = self.parsed
            with patch.object(agent_cli_app, "_main_async", new=self.main_async):
                with patch.object(agent_cli_app.asyncio, "run") as run_call:
                    self.run_call = run_call
                    agent_cli_module.main()

    def assert_called_once_with(self) -> None:
        self.parser.parse_args.assert_called_once_with()
        self.main_async.assert_called_once_with(self.parsed)
        self.run_call.assert_called_once_with(self.entrypoint)
