from __future__ import annotations

import unittest
from importlib import import_module
from typing import Any

runtime_shell = import_module("core.orchestra_agents.launch._runtime_shell")
ShellResult = runtime_shell.ShellResult
checked_command = runtime_shell.checked_command


class _FakeShellRunner:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.calls: list[tuple[Any, int]] = []

    def __call__(self, command: list[str], *, timeout: int = 120) -> Any:
        self.calls.append((command, timeout))
        return self.result


class RuntimeShellTests(unittest.TestCase):
    def test_checked_command_returns_success_result(self) -> None:
        runner = _FakeShellRunner(ShellResult(0, stdout="ok\n"))

        result = checked_command(runner, ["cmd", "run"], timeout=9, error_message="fallback")

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "ok\n")
        self.assertEqual(runner.calls, [(["cmd", "run"], 9)])

    def test_checked_command_prefers_stderr_message(self) -> None:
        runner = _FakeShellRunner(ShellResult(3, stderr="boom\n"))

        with self.assertRaisesRegex(RuntimeError, r"^boom$"):
            checked_command(runner, ["cmd"], timeout=5, error_message="fallback")

    def test_checked_command_uses_fallback(self) -> None:
        runner = _FakeShellRunner(ShellResult(4, stderr=""))

        with self.assertRaisesRegex(RuntimeError, r"^fallback error$"):
            checked_command(runner, ["cmd"], timeout=5, error_message="fallback error")
