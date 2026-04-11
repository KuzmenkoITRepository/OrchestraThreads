"""Dispatch helpers for the generic codex-backed agent_mux runtime."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgentMuxDispatchSpec:
    """Minimal stdin payload builder for agent-mux."""

    dispatch_id: str
    prompt: str
    cwd: str
    artifact_dir: str
    system_prompt: str = ""
    role: str | None = None
    variant: str | None = None
    engine: str = "codex"
    model: str | None = None
    effort: str = "high"
    timeout_sec: int | None = None
    context_file: str | None = None
    full_access: bool = True
    engine_opts: dict[str, Any] | None = None

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


def parse_agent_mux_result(stdout_text: str) -> dict[str, Any]:
    """Parse the final JSON object emitted by agent-mux."""

    lines = tuple(_nonempty_lines(stdout_text))
    if not lines:
        raise RuntimeError("agent-mux produced no stdout")
    for line in reversed(lines):
        payload = _parse_json_object(line)
        if payload is not None:
            return payload
    raise RuntimeError("agent-mux did not produce a JSON result")


def _nonempty_lines(stdout_text: str) -> list[str]:
    lines = str(stdout_text or "").splitlines()
    return [line.strip() for line in lines if line.strip()]


def _parse_json_object(line: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, dict):
        return payload
    return None
