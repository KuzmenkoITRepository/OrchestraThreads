"""Helpers for keeping active OrchestraThreads invocation context out of the LLM prompt."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ACTIVE_CONTEXT_PATH = Path(
    os.getenv(
        "ORCHESTRA_THREADS_ACTIVE_CONTEXT_PATH",
        "/tmp/orchestra_threads_active_context.json",
    )
)


def write_active_context(payload: dict[str, Any]) -> None:
    """Persist the currently active thread invocation for local MCP tools."""
    ACTIVE_CONTEXT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = ACTIVE_CONTEXT_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(ACTIVE_CONTEXT_PATH)


def read_active_context() -> dict[str, Any]:
    """Load the active invocation context if present."""
    if not ACTIVE_CONTEXT_PATH.exists():
        return {}
    try:
        raw = ACTIVE_CONTEXT_PATH.read_text(encoding="utf-8").strip()
        if not raw:
            return {}
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def clear_active_context() -> None:
    """Remove any stale active invocation context."""
    try:
        ACTIVE_CONTEXT_PATH.unlink()
    except FileNotFoundError:
        return
