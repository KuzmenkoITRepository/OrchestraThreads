from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_DEFAULT_THREADS_URL = "http://127.0.0.1:8788"
_DEFAULT_THREADS_COMMAND = ("python", "-m", "core.orchestra_thread.mcp_server")


def build_threads_block(
    config_dir: Path,
    server: dict[str, Any],
    agent_slug: str,
    working_dir: str,
) -> dict[str, Any]:
    return {
        "type": "local",
        "command": _server_command(server),
        "environment": _server_env(server, config_dir, agent_slug, working_dir),
    }


def _server_command(server: dict[str, Any]) -> list[str]:
    raw_command = server.get("command") or _DEFAULT_THREADS_COMMAND[0]
    command = [str(raw_command).strip() or _DEFAULT_THREADS_COMMAND[0]]
    args = server.get("args")
    if isinstance(args, list):
        command.extend([str(arg) for arg in args])
    if len(command) == 1:
        command.extend(list(_DEFAULT_THREADS_COMMAND[1:]))
    return command


def _server_env(
    server: dict[str, Any],
    config_dir: Path,
    agent_slug: str,
    working_dir: str,
) -> dict[str, str]:
    raw_env = server.get("env")
    env = raw_env if isinstance(raw_env, dict) else {}
    raw_threads_url = env.get("ORCHESTRA_THREADS_URL") or os.getenv("ORCHESTRA_THREADS_URL")
    if raw_threads_url:
        threads_url = str(raw_threads_url).strip()
    else:
        threads_url = _DEFAULT_THREADS_URL
    active_context_path = config_dir.parent / "state" / "active_context.json"
    return {
        "PYTHONPATH": str(env.get("PYTHONPATH") or working_dir),
        "ORCHESTRA_THREADS_URL": threads_url,
        "ORCHESTRA_THREADS_AGENT_SLUG": agent_slug,
        "ORCHESTRA_THREADS_ACTIVE_CONTEXT_PATH": str(active_context_path),
    }
