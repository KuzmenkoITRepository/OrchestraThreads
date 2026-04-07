from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class CommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


class AsyncCommandRunner(Protocol):
    async def run(
        self,
        *,
        args: Sequence[str],
        cwd: Path,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult: ...


class CommandRunner:
    async def run(
        self,
        *,
        args: Sequence[str],
        cwd: Path,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        process = await asyncio.create_subprocess_exec(
            *args,
            cwd=str(cwd),
            env=_merged_env(env),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_data, stderr_data = await process.communicate()
        return CommandResult(
            args=tuple(str(item) for item in args),
            returncode=int(process.returncode or 0),
            stdout=stdout_data.decode("utf-8", errors="replace").strip(),
            stderr=stderr_data.decode("utf-8", errors="replace").strip(),
        )


def _merged_env(env: Mapping[str, str] | None) -> dict[str, str]:
    merged = dict(os.environ)
    if env is not None:
        for key, value in env.items():
            merged[key] = str(value)
    return merged
