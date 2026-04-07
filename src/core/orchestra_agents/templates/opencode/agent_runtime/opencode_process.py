"""Subprocess management for ``opencode serve``."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from pathlib import Path

from aiohttp import ClientError

from core.orchestra_agents.templates.opencode.agent_runtime.opencode_client import (
    OpencodeClient,
    close_client,
)

_LOGGER = logging.getLogger(__name__)
_TERM_WAIT_SECONDS = 5.0


class OpencodeProcess:
    """Manages the lifecycle of an ``opencode serve`` subprocess."""

    def __init__(self, *, state_dir: Path, config_path: Path, port: int) -> None:
        self._state_dir = state_dir
        self._config_path = config_path
        self._port = int(port)
        self._process: asyncio.subprocess.Process | None = None

    @property
    def port(self) -> int:
        return self._port

    def is_alive(self) -> bool:
        process = self._process
        return bool(process and process.returncode is None)

    async def start(self) -> None:
        if self.is_alive():
            return
        _ensure_xdg_dirs(self._state_dir)
        self._process = await asyncio.create_subprocess_exec(
            *_serve_command(self._port),
            cwd=str(self._state_dir),
            env=_build_env(self._state_dir, self._config_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    async def wait_ready(self, timeout: float) -> None:
        await _poll_readiness(self._process, self._port, timeout)

    async def stop(self) -> None:
        process = self._process
        if process is None:
            return
        self._process = None
        await _terminate_process(process)


def _serve_command(port: int) -> list[str]:
    return ["opencode", "serve", "--hostname", "127.0.0.1", "--port", str(port), "--pure"]


def _build_env(state_dir: Path, config_path: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["XDG_CONFIG_HOME"] = str(state_dir / "xdg_config")
    env["XDG_DATA_HOME"] = str(state_dir / "xdg_data")
    env["XDG_CACHE_HOME"] = str(state_dir / "xdg_cache")
    env["XDG_STATE_HOME"] = str(state_dir / "xdg_state")
    env["OPENCODE_CONFIG"] = str(config_path)
    return env


def _ensure_xdg_dirs(state_dir: Path) -> None:
    for subdir in ("xdg_config", "xdg_data", "xdg_cache", "xdg_state"):
        (state_dir / subdir).mkdir(parents=True, exist_ok=True)


async def _poll_readiness(
    process: asyncio.subprocess.Process | None,
    port: int,
    timeout: float,
) -> None:
    deadline = asyncio.get_running_loop().time() + max(timeout, 0.1)
    last_error: Exception | None = None
    while asyncio.get_running_loop().time() < deadline:
        if process is None or process.returncode is not None:
            raise RuntimeError("opencode serve process exited before readiness")
        is_ready, last_error = await _readiness_attempt(port)
        if is_ready:
            return
        await asyncio.sleep(0.2)
    msg = "opencode serve readiness timeout"
    raise RuntimeError(msg) from last_error


async def _readiness_attempt(port: int) -> tuple[bool, Exception | None]:
    client = OpencodeClient(f"http://127.0.0.1:{port}")
    try:
        await client.list_sessions()
    except (RuntimeError, OSError, ClientError) as exc:
        return False, exc
    finally:
        await close_client(client)
    return True, None


async def _terminate_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    process.send_signal(signal.SIGTERM)
    try:
        await asyncio.wait_for(process.wait(), timeout=_TERM_WAIT_SECONDS)
    except TimeoutError:
        _LOGGER.warning("opencode serve did not stop after SIGTERM; sending SIGKILL")
        process.send_signal(signal.SIGKILL)
        await process.wait()
