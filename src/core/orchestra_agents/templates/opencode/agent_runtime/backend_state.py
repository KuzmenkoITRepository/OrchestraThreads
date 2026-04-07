from __future__ import annotations

import asyncio
import os
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.orchestra_agents.runtime.contracts import AgentEvent


@dataclass(frozen=True)
class RuntimePaths:
    root: Path
    config_dir: Path
    state_dir: Path
    active_context: Path

    @classmethod
    def from_working_dir(cls, working_dir: str) -> RuntimePaths:
        state_root = os.getenv("OPENCODE_RUNTIME_STATE_ROOT")
        if state_root:
            root = Path(state_root)
        else:
            root = Path(working_dir) / "runtime_state" / "opencode"
        return cls(
            root=root,
            config_dir=root / "config",
            state_dir=root / "state",
            active_context=(root / "state" / "active_context.json"),
        )

    def ensure(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)


@dataclass
class DispatchState:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    task: asyncio.Task[None] | None = None
    event: AgentEvent | None = None
    last_result: dict[str, Any] = field(default_factory=dict)


@dataclass
class DedupState:
    limit: int
    seen_ids: set[str] = field(default_factory=set)
    order: deque[str] = field(default_factory=deque)

    def contains(self, event_id: str) -> bool:
        return event_id in self.seen_ids

    def remember(self, event_id: str) -> None:
        self.seen_ids.add(event_id)
        self.order.append(event_id)
        while len(self.order) > self.limit:
            oldest = self.order.popleft()
            self.seen_ids.discard(oldest)


@dataclass
class Components:
    process: Any = None
    client: Any = None
    session_manager: Any = None
    dispatcher: Any = None
