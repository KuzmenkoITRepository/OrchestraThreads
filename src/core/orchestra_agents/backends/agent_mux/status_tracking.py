from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StatusTracker:
    queued_event_id: str | None = None
    queued_event_ids: list[str] = field(default_factory=list)
    duplicate_events: int = 0
    dispatch_id: str | None = None
    dispatch_status: str | None = None
    dispatch_reason: str | None = None
    reply_preview: str | None = None
    processed_event_id: str | None = None
    processed_event_kind: str | None = None
    tool_calls: list[str] = field(default_factory=list)

    def mark_queued(self, *, queued_event_ids: list[str], duplicate_events: int) -> None:
        self.queued_event_ids = queued_event_ids
        self.queued_event_id = queued_event_ids[-1] if queued_event_ids else None
        self.duplicate_events = duplicate_events

    def mark_processing_event(self, event: Any) -> None:
        self.processed_event_id = event.event_id
        self.processed_event_kind = event.event_kind

    def mark_running_dispatch(self, dispatch_id: str) -> None:
        self.dispatch_id = dispatch_id
        self.dispatch_status = "running"
        self.dispatch_reason = None
        self.tool_calls = []
        self.reply_preview = None

    def mark_failed_dispatch(self, reason: str) -> None:
        self.dispatch_status = "failed"
        self.dispatch_reason = reason

    def mark_completed_dispatch(
        self,
        status: str,
        tool_calls: list[str],
        reason: str | None,
        preview: str | None,
    ) -> None:
        self.dispatch_status = status
        self.dispatch_reason = reason
        self.tool_calls = tool_calls
        self.reply_preview = preview

    def reset(self) -> None:
        self.queued_event_id = None
        self.queued_event_ids = []
        self.duplicate_events = 0
        self.dispatch_id = None
        self.dispatch_status = None
        self.dispatch_reason = None
        self.reply_preview = None
        self.processed_event_id = None
        self.processed_event_kind = None
        self.tool_calls = []
