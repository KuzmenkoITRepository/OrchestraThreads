from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_DEFAULT_THREADS_URL = "http://127.0.0.1:8788"
_DEFAULT_THREADS_COMMAND = ("python", "-m", "core.orchestra_thread.mcp.server")


def render_server_config(
    *,
    config_dir: Path,
    server: dict[str, Any],
    agent_slug: str,
    working_dir: str,
) -> dict[str, Any]:
    return {
        "type": "local",
        "command": _server_command(server),
        "environment": _server_env(
            config_dir=config_dir,
            server=server,
            agent_slug=agent_slug,
            working_dir=working_dir,
        ),
    }


def _server_command(server: dict[str, Any]) -> list[str]:
    raw_command = server.get("command") or _DEFAULT_THREADS_COMMAND[0]
    command = [str(raw_command).strip() or _DEFAULT_THREADS_COMMAND[0]]
    raw_args = server.get("args")
    if isinstance(raw_args, list):
        command.extend(str(arg) for arg in raw_args)
    if len(command) == 1:
        command.extend(_DEFAULT_THREADS_COMMAND[1:])
    return command


def _server_env(
    *,
    config_dir: Path,
    server: dict[str, Any],
    agent_slug: str,
    working_dir: str,
) -> dict[str, str]:
    raw_env = server.get("env")
    env = raw_env if isinstance(raw_env, dict) else {}
    merged = {key: str(value) for key, value in env.items()}
    return _with_threads_defaults(
        config_dir=config_dir,
        environment=merged,
        server_name=str(server.get("name") or "").strip(),
        agent_slug=agent_slug,
        working_dir=working_dir,
    )


def _with_threads_defaults(
    *,
    config_dir: Path,
    environment: dict[str, str],
    server_name: str,
    agent_slug: str,
    working_dir: str,
) -> dict[str, str]:
    merged = dict(environment)
    if server_name != "orchestra_threads":
        return merged
    active_context_path = config_dir.parent / "state" / "active_context.json"
    merged.setdefault("PYTHONPATH", working_dir)
    merged.setdefault(
        "ORCHESTRA_THREADS_URL",
        _threads_url(environment),
    )
    merged.setdefault("ORCHESTRA_THREADS_AGENT_SLUG", agent_slug)
    merged.setdefault("ORCHESTRA_THREADS_ACTIVE_CONTEXT_PATH", str(active_context_path))
    return merged


def _threads_url(environment: dict[str, str]) -> str:
    raw_threads_url = environment.get("ORCHESTRA_THREADS_URL") or os.getenv("ORCHESTRA_THREADS_URL")
    if raw_threads_url:
        return str(raw_threads_url).strip()
    return _DEFAULT_THREADS_URL
