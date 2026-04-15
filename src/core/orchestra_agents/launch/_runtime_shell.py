"""Tiny shell boundary for launch runtimes.

Pure seam: command runner protocol, shell result value, checked-command helper.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ShellResult:
    """Result from shell command execution."""

    returncode: int
    stdout: str = ""
    stderr: str = ""


class ShellCommandRunner(Protocol):
    """Callable shell boundary for launch runtimes."""

    def __call__(self, command: list[str], *, timeout: int = 120) -> ShellResult: ...


def checked_command(
    runner: ShellCommandRunner,
    command: list[str],
    *,
    timeout: int,
    error_message: str,
) -> ShellResult:
    """Run command and raise stable runtime error on non-zero exit."""

    result = runner(command, timeout=timeout)
    if result.returncode == 0:
        return result
    raise RuntimeError(result.stderr.strip() or error_message)
