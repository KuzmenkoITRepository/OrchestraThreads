from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ShellCall = tuple[list[str], int]


@dataclass
class PrefixCommandCapture:
    prefix: tuple[str, ...]
    result: Any
    calls: list[list[str]] = field(default_factory=list)

    @property
    def last_command(self) -> list[str]:
        if self.calls:
            return self.calls[-1]
        return []

    def matches(self, command: list[str]) -> bool:
        return command[: len(self.prefix)] == list(self.prefix)

    def record(self, command: list[str]) -> Any:
        self.calls.append(list(command))
        return self.result


@dataclass
class QueueShellRunner:
    responses: list[Any] = field(default_factory=list)
    calls: list[ShellCall] = field(default_factory=list)

    def __call__(self, command: list[str], *, timeout: int = 120) -> Any:
        self.calls.append((list(command), timeout))
        if not self.responses:
            raise AssertionError(f"unexpected command: {command}")
        return self.responses.pop(0)

    def push(self, result: Any) -> None:
        self.responses.append(result)

    def push_many(self, *results: Any) -> None:
        self.responses.extend(results)


@dataclass
class MappingShellRunner:
    responses: dict[tuple[str, ...], Any]
    captures: tuple[PrefixCommandCapture, ...] = ()
    calls: list[list[str]] = field(default_factory=list)

    def __call__(self, command: list[str], *, timeout: int = 120) -> Any:
        timeout_is_valid = timeout >= 0
        if not timeout_is_valid:
            raise AssertionError("timeout must be non-negative")
        recorded_command = list(command)
        self.calls.append(recorded_command)
        for capture in self.captures:
            if capture.matches(recorded_command):
                return capture.record(recorded_command)
        key = tuple(recorded_command)
        if key not in self.responses:
            raise AssertionError(f"unexpected docker command: {command}")
        return self.responses[key]
