"""SGR backend status tracking."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SGRBackendStatus:
    """Tracks the last-known state of the SGR backend for status reporting."""

    thread_id: str | None = None
    peer_agent_slug: str | None = None
    reply_preview: str | None = None
    status_preview: str | None = None
    published_status: str | None = None
    ignored_output_preview: str | None = None
    llm_model: str | None = None
    delivery_duplicate: bool = False
    action_emitted: bool = False
    tool_actions: list[str] = field(default_factory=list)
    total_turns: int = 0
    total_tool_calls: int = 0
    total_tool_errors: int = 0
    total_messages_sent: int = 0
    total_statuses_published: int = 0

    def reset(self) -> None:
        self.thread_id = None
        self.peer_agent_slug = None
        self.reply_preview = None
        self.status_preview = None
        self.published_status = None
        self.ignored_output_preview = None
        self.llm_model = None
        self.delivery_duplicate = False
        self.action_emitted = False
        self.tool_actions = []
        self.total_turns = 0
        self.total_tool_calls = 0
        self.total_tool_errors = 0
        self.total_messages_sent = 0
        self.total_statuses_published = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "last_thread_id": self.thread_id,
            "last_peer_agent_slug": self.peer_agent_slug,
            "last_reply_preview": self.reply_preview,
            "last_status_preview": self.status_preview,
            "last_published_status": self.published_status,
            "last_ignored_output_preview": self.ignored_output_preview,
            "last_delivery_duplicate": self.delivery_duplicate,
            "last_action_emitted": self.action_emitted,
            "last_tool_actions": list(self.tool_actions),
            "total_turns": self.total_turns,
            "total_tool_calls": self.total_tool_calls,
            "total_tool_errors": self.total_tool_errors,
            "total_messages_sent": self.total_messages_sent,
            "total_statuses_published": self.total_statuses_published,
        }
