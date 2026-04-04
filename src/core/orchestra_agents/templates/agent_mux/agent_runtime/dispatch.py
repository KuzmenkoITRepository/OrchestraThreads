"""Dispatch helpers for the generic codex-backed agent_mux runtime."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from core.llm_proxy.client_config import build_llm_proxy_openai_base_url


def _toml_quote(value: str) -> str:
    return json.dumps(str(value))


def _toml_bool(value: bool) -> str:
    return "true" if bool(value) else "false"


class _FormatDict(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _render_scalar(value: Any, variables: Mapping[str, str]) -> str:
    return str(value if value is not None else "").format_map(_FormatDict(**variables))


def _render_list(values: Sequence[Any] | None, variables: Mapping[str, str]) -> list[str]:
    rendered: list[str] = []
    for item in values or []:
        rendered.append(_render_scalar(item, variables))
    return rendered


def _render_dict(values: Mapping[str, Any] | None, variables: Mapping[str, str]) -> dict[str, str]:
    rendered: dict[str, str] = {}
    for key, value in (values or {}).items():
        rendered[str(key)] = _render_scalar(value, variables)
    return rendered


@dataclass(frozen=True)
class AgentMuxDispatchSpec:
    """Minimal stdin payload builder for agent-mux."""

    dispatch_id: str
    prompt: str
    cwd: str
    artifact_dir: str
    system_prompt: str = ""
    role: Optional[str] = None
    variant: Optional[str] = None
    engine: str = "codex"
    model: Optional[str] = None
    effort: str = "high"
    timeout_sec: Optional[int] = None
    context_file: Optional[str] = None
    full_access: bool = True
    engine_opts: Optional[dict[str, Any]] = None

    def to_stdin_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "dispatch_id": self.dispatch_id,
            "engine": self.engine,
            "prompt": self.prompt,
            "cwd": self.cwd,
            "artifact_dir": self.artifact_dir,
            "effort": self.effort,
            "full_access": self.full_access,
        }
        if self.system_prompt:
            payload["system_prompt"] = self.system_prompt
        if self.role:
            payload["role"] = self.role
        if self.variant:
            payload["variant"] = self.variant
        if self.model:
            payload["model"] = self.model
        if self.timeout_sec is not None:
            payload["timeout_sec"] = int(self.timeout_sec)
        if self.context_file:
            payload["context_file"] = self.context_file
        if self.engine_opts:
            payload["engine_opts"] = dict(self.engine_opts)
        return payload


def build_agent_mux_command(binary: str = "agent-mux") -> list[str]:
    """Return the canonical stdin-driven agent-mux command."""

    return [str(binary or "agent-mux").strip() or "agent-mux", "--stdin"]


def write_runtime_codex_config(
    *,
    codex_home: Path,
    llm_proxy_url: str,
    route_policy: str,
    model: str,
    agent_slug: str,
    active_context_path: str,
    pythonpath: str,
    agent_working_dir: str,
    mcp_servers: Sequence[Mapping[str, Any]] | None = None,
) -> Path:
    """Write a user-level Codex config under the runtime home."""

    config_root = codex_home / ".codex"
    config_root.mkdir(parents=True, exist_ok=True)
    config_path = config_root / "config.toml"
    base_url = build_llm_proxy_openai_base_url(route_policy, proxy_url=llm_proxy_url)
    lines = [
        f"model = {_toml_quote(model)}",
        "model_provider = \"llm_proxy\"",
        "",
        "[model_providers.llm_proxy]",
        "name = \"LLM Proxy\"",
        f"base_url = {_toml_quote(base_url)}",
        "env_key = \"LLM_PROXY_API_KEY\"",
        "wire_api = \"responses\"",
        "env_http_headers = { \"X-Orchestra-Agent-Slug\" = \"ORCHESTRA_AGENT_SLUG\", \"X-Orchestra-Context-Id\" = \"ORCHESTRA_CONTEXT_ID\", \"X-Orchestra-Langfuse-Session-Id\" = \"ORCHESTRA_CONTEXT_ID\" }",
        "",
    ]

    variables = {
        "agent_slug": str(agent_slug),
        "active_context_path": str(active_context_path),
        "pythonpath": str(pythonpath),
        "agent_working_dir": str(agent_working_dir),
        "working_dir": str(agent_working_dir),
    }
    for item in mcp_servers or []:
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("name") or "").strip()
        command = str(item.get("command") or "").strip()
        if not name or not command:
            continue
        args = _render_list(item.get("args"), variables)
        env = _render_dict(item.get("env"), variables)
        cwd = _render_scalar(item.get("cwd"), variables).strip() if item.get("cwd") is not None else ""
        enabled_tools = _render_list(item.get("enabled_tools"), variables)
        lines.extend(
            [
                f"[mcp_servers.{name}]",
                f"command = {_toml_quote(_render_scalar(command, variables))}",
            ]
        )
        if args:
            lines.append(f"args = {json.dumps(args, ensure_ascii=False)}")
        if cwd:
            lines.append(f"cwd = {_toml_quote(cwd)}")
        if item.get("startup_timeout_sec") is not None:
            lines.append(f"startup_timeout_sec = {int(item.get('startup_timeout_sec'))}")
        if item.get("required") is not None:
            lines.append(f"required = {_toml_bool(bool(item.get('required')))}")
        if item.get("enabled") is not None:
            lines.append(f"enabled = {_toml_bool(bool(item.get('enabled')))}")
        if enabled_tools:
            lines.append(f"enabled_tools = {json.dumps(enabled_tools, ensure_ascii=False)}")
        lines.append("")
        if env:
            lines.append(f"[mcp_servers.{name}.env]")
            for key, value in env.items():
                lines.append(f"{key} = {_toml_quote(value)}")
            lines.append("")

    config_path.write_text("\n".join(lines), encoding="utf-8")
    return config_path


def parse_agent_mux_result(stdout_text: str) -> dict[str, Any]:
    """Parse the final JSON object emitted by agent-mux."""

    lines = [line.strip() for line in str(stdout_text or "").splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("agent-mux produced no stdout")
    for line in reversed(lines):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise RuntimeError("agent-mux did not produce a JSON result")
