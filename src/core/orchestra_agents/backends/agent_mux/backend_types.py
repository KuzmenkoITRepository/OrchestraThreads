from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AgentMuxRunRequest:
    event: Any
    dispatch_id: str
    artifact_dir: Path
    working_dir: str
    agent_slug: str
    context_id: str
    system_prompt: str
    settings: Any
    prompt: str
    active_context_path: str


@dataclass(frozen=True)
class AgentTurnContext:
    runtime_state: Any
    context_id: str
    event: Any
    max_entries: int


@dataclass(frozen=True)
class AgentOutputContext:
    runtime_state: Any
    context_id: str
    agent_slug: str
    event: Any
    max_entries: int
