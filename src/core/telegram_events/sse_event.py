"""SSE event data structure — no dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SSEEvent:
    """Parsed SSE event from better-telegram-mcp."""

    event_id: str
    event_type: str
    occurred_at: str
    mode: str
    account: str
    update: dict[str, Any]
