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


@dataclass(frozen=True)
class _ServerOptionalConfig:
    startup_timeout: Any
    required: Any
    enabled: Any


def render_server_block(item: ServerItem, variables: ServerVariables) -> list[str]:
    name = str(item.get("name") or "").strip()
    if not name:
        return []
    command = str(item.get("command") or "").strip()
    if not command:
        return []
    return _render_named_server_block(item, variables, name=name, command=command)


def _render_named_server_block(
    item: ServerItem,
    variables: ServerVariables,
    *,
    name: str,
    command: str,
) -> list[str]:
    server = _render_server_settings(item=item, variables=variables)
    lines = [f"[mcp_servers.{name}]", f"command = {toml_quote(command)}"]
    _append_optional_server_lines(
        lines=lines,
        args=server["args"],
        cwd=server["cwd"],
        enabled_tools=server["enabled_tools"],
        optional=_ServerOptionalConfig(
            startup_timeout=item.get("startup_timeout_sec"),
            required=item.get("required"),
            enabled=item.get("enabled"),
        ),
    )
    lines.append("")
    if server["env"]:
        lines.extend(_render_env_lines(name=name, env=server["env"]))
    return lines


def _render_server_settings(*, item: ServerItem, variables: ServerVariables) -> dict[str, Any]:
    rendered_cwd = ""
    if item.get("cwd") is not None:
        rendered_cwd = render_scalar(item.get("cwd"), variables).strip()
    return {
        "args": render_list(item.get("args"), variables),
        "env": render_dict(item.get("env"), variables),
        "cwd": rendered_cwd,
        "enabled_tools": render_list(item.get("enabled_tools"), variables),
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
        lines.append(f"args = {json.dumps(args, ensure_ascii=False)}")
    if cwd:
        lines.append(f"cwd = {toml_quote(cwd)}")
    if optional.startup_timeout is not None:
        lines.append(f"startup_timeout_sec = {_startup_timeout_value(optional.startup_timeout)}")
    if optional.required is not None:
        lines.append(f"required = {toml_bool(bool(optional.required))}")
    if optional.enabled is not None:
        lines.append(f"enabled = {toml_bool(bool(optional.enabled))}")
    if enabled_tools:
        lines.append(f"enabled_tools = {json.dumps(enabled_tools, ensure_ascii=False)}")


def _render_env_lines(*, name: str, env: ServerVariables) -> list[str]:
    lines = [f"[mcp_servers.{name}.env]"]
    for key, value in env.items():
        lines.append(f"{key} = {toml_quote(value)}")
    lines.append("")
    return lines


def _startup_timeout_value(value: Any) -> int:
    normalized = str(value or "").strip() or "0"
    return int(normalized)
