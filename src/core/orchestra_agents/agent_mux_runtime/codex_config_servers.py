from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from core.orchestra_agents.agent_mux_runtime.config_interpolation import (
    render_dict,
    render_list,
    render_scalar,
)
from core.orchestra_agents.agent_mux_runtime.toml_rendering import toml_bool, toml_quote

ServerItem = Mapping[str, Any]
ServerVariables = Mapping[str, str]
MCP_SERVERS_PREFIX = "[mcp_servers."
MCP_SERVER_ENV_SUFFIX = ".env]"
SERVER_BLOCK_SUFFIX = "]"
ARGS_FIELD = "args"
CWD_FIELD = "cwd"
ENABLED_TOOLS_FIELD = "enabled_tools"
STARTUP_TIMEOUT_FIELD = "startup_timeout_sec"
REQUIRED_FIELD = "required"
ENABLED_FIELD = "enabled"


@dataclass(frozen=True)
class _ServerOptionalConfig:
    startup_timeout: Any
    required: Any
    enabled: Any


def render_server_block(server_item: ServerItem, variables: ServerVariables) -> list[str]:
    name = str(server_item.get("name") or "").strip()
    if not name:
        return []
    command = str(server_item.get("command") or "").strip()
    if not command:
        return []
    return _render_named_server_block(server_item, variables, name=name, command=command)


def _render_named_server_block(
    server_item: ServerItem,
    variables: ServerVariables,
    *,
    name: str,
    command: str,
) -> list[str]:
    server = _render_server_settings(server_item=server_item, variables=variables)
    lines = [f"{MCP_SERVERS_PREFIX}{name}{SERVER_BLOCK_SUFFIX}", f"command = {toml_quote(command)}"]
    _append_optional_server_lines(
        lines=lines,
        args=server[ARGS_FIELD],
        cwd=server[CWD_FIELD],
        enabled_tools=server[ENABLED_TOOLS_FIELD],
        optional=_ServerOptionalConfig(
            startup_timeout=server_item.get("startup_timeout_sec"),
            required=server_item.get("required"),
            enabled=server_item.get("enabled"),
        ),
    )
    lines.append("")
    if server["env"]:
        lines.extend(_render_env_lines(name=name, env=server["env"]))
    return lines


def _render_server_settings(
    *, server_item: ServerItem, variables: ServerVariables
) -> dict[str, Any]:
    rendered_cwd = ""
    if server_item.get("cwd") is not None:
        rendered_cwd = render_scalar(server_item.get("cwd"), variables).strip()
    return {
        ARGS_FIELD: render_list(server_item.get(ARGS_FIELD), variables),
        "env": render_dict(server_item.get("env"), variables),
        CWD_FIELD: rendered_cwd,
        ENABLED_TOOLS_FIELD: render_list(server_item.get(ENABLED_TOOLS_FIELD), variables),
    }


def _append_optional_server_lines(
    *,
    lines: list[str],
    args: list[str],
    cwd: str,
    enabled_tools: list[str],
    optional: _ServerOptionalConfig,
) -> None:
    if args:
        lines.append(f"{ARGS_FIELD} = {json.dumps(args, ensure_ascii=False)}")
    if cwd:
        lines.append(f"{CWD_FIELD} = {toml_quote(cwd)}")
    if optional.startup_timeout is not None:
        lines.append(
            f"{STARTUP_TIMEOUT_FIELD} = {_startup_timeout_value(optional.startup_timeout)}"
        )
    if optional.required is not None:
        lines.append(f"{REQUIRED_FIELD} = {toml_bool(bool(optional.required))}")
    if optional.enabled is not None:
        lines.append(f"{ENABLED_FIELD} = {toml_bool(bool(optional.enabled))}")
    if enabled_tools:
        lines.append(f"{ENABLED_TOOLS_FIELD} = {json.dumps(enabled_tools, ensure_ascii=False)}")


def _render_env_lines(*, name: str, env: ServerVariables) -> list[str]:
    lines = [f"[mcp_servers.{name}{MCP_SERVER_ENV_SUFFIX}"]
    for env_key, env_value in env.items():
        lines.append(f"{env_key} = {toml_quote(env_value)}")
    lines.append("")
    return lines


def _startup_timeout_value(value: Any) -> int:
    normalized = str(value or "").strip() or "0"
    return int(normalized)
