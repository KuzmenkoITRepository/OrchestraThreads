from __future__ import annotations

import json
from pathlib import Path

from core.orchestra_agents.runtime.contracts import AgentEvent


def write_active_context(
    path: Path,
    event: AgentEvent,
    context_id: str,
    agent_slug: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, str | None] = {
        "context_id": context_id,
        "event_id": event.event_id,
        "event_kind": event.event_kind,
        "thread_id": event.thread_id,
        "from_agent_slug": event.from_agent_slug,
        "agent_slug": agent_slug,
    }
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(path)


def clear_file(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
