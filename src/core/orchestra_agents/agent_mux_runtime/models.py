"""Shared data models for agent_mux runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgentMuxRuntimeSettings:
    http_endpoint: str
    agent_mux_binary: str
    state_root: str
    artifact_root: str
    role: str | None
    variant: str | None
    engine: str
    max_attempts: int
    omniroute_url: str
    omniroute_api_key: str
    llm_route_policy: str
    default_model: str
    agent_timeout_seconds: int
    context_memory_entries: int
    require_tool_call_for_response: bool
    mcp_servers: tuple[dict[str, Any], ...]
