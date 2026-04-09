from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentMuxBackendStatus:
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
