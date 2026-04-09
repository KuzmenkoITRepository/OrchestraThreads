"""Runtime session state for event-centric session routing."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC
from pathlib import Path
from typing import Any

from core.orchestra_agents.backends.agent_mux.internal.event_types import NormalizedEvent
from core.orchestra_agents.backends.agent_mux.internal.json_store import (
    read_json_object,
    write_json_object,
)
from core.orchestra_agents.backends.agent_mux.internal.session_types import (
    RoutingKey,
    SessionId,
    SessionLifecycle,
)


@dataclass
class RuntimeSession:
    """
    Internal runtime session state.

    Each session owns:
    - a generated internal session_id
    - one canonical routing_key used only inside the backend
    - lifecycle state
    - mailbox of pending events
    - native CLI session handle/metadata
    - compact runtime timeline
    - artifact directory
    - idempotency ledger for recent processed event IDs
    """

    session_id: SessionId
    routing_key: RoutingKey
    lifecycle: SessionLifecycle
    mailbox: list[NormalizedEvent] = field(default_factory=list)
    cli_session_metadata: dict[str, Any] = field(default_factory=dict)
    timeline: list[dict[str, Any]] = field(default_factory=list)
    artifact_dir: Path | None = None
    processed_event_ids: set[str] = field(default_factory=set)
    created_at: str = ""
    updated_at: str = ""

    def append_event(self, event: NormalizedEvent) -> None:
        """Append event to session mailbox."""
        if event.event_id in self.processed_event_ids:
            return  # Idempotency: skip duplicate events
        self.mailbox.append(event)

    def claim_next_event(self) -> NormalizedEvent | None:
        """Claim next event from mailbox."""
        if not self.mailbox:
            return None
        return self.mailbox.pop(0)

    def mark_event_processed(self, event_id: str) -> None:
        """Mark event as processed for idempotency."""
        self.processed_event_ids.add(event_id)
        # Keep ledger bounded
        if len(self.processed_event_ids) > 100:
            oldest = list(self.processed_event_ids)[:50]
            self.processed_event_ids -= set(oldest)

    def add_timeline_entry(self, event_type: str, metadata: dict[str, Any] | None = None) -> None:
        """Add entry to runtime timeline."""
        from datetime import datetime

        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": event_type,
            "metadata": metadata or {},
        }
        self.timeline.append(entry)
        # Keep timeline bounded
        if len(self.timeline) > 50:
            self.timeline = self.timeline[-50:]

    def to_dict(self) -> dict[str, Any]:
        """Serialize session state to dict."""
        return {
            "session_id": self.session_id,
            "routing_key": self.routing_key,
            "lifecycle": self.lifecycle.value,
            "mailbox": [
                {
                    "event_id": e.event_id,
                    "source": e.source,
                    "routing_key": e.routing_key,
                    "kind": e.kind,
                    "payload": e.payload,
                    "created_at": e.created_at,
                    "interrupt": e.interrupt,
                    "priority": e.priority,
                    "metadata": e.metadata,
                }
                for e in self.mailbox
            ],
            "cli_session_metadata": self.cli_session_metadata,
            "timeline": self.timeline,
            "artifact_dir": str(self.artifact_dir) if self.artifact_dir else None,
            "processed_event_ids": list(self.processed_event_ids),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuntimeSession:
        """Deserialize session state from dict."""
        mailbox = [
            NormalizedEvent(
                event_id=e["event_id"],
                source=e["source"],
                routing_key=e["routing_key"],
                kind=e["kind"],
                payload=e["payload"],
                created_at=e["created_at"],
                interrupt=e.get("interrupt", False),
                priority=e.get("priority", 10),
                metadata=e.get("metadata", {}),
            )
            for e in data.get("mailbox", [])
        ]
        artifact_dir = Path(data["artifact_dir"]) if data.get("artifact_dir") else None
        return cls(
            session_id=SessionId(data["session_id"]),
            routing_key=RoutingKey(data["routing_key"]),
            lifecycle=SessionLifecycle(data["lifecycle"]),
            mailbox=mailbox,
            cli_session_metadata=data.get("cli_session_metadata", {}),
            timeline=data.get("timeline", []),
            artifact_dir=artifact_dir,
            processed_event_ids=set(data.get("processed_event_ids", [])),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )


def save_session_state(session: RuntimeSession, state_root: Path) -> None:
    """Save session state to persistent storage."""
    session_dir = state_root / "sessions" / session.session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    state_file = session_dir / "session_state.json"

    from datetime import datetime

    session.updated_at = datetime.now(UTC).isoformat()

    write_json_object(state_file, session.to_dict())


def load_session_state(session_id: SessionId, state_root: Path) -> RuntimeSession | None:
    """Load session state from persistent storage."""
    state_file = state_root / "sessions" / session_id / "session_state.json"
    if not state_file.exists():
        return None
    data = read_json_object(state_file)
    return RuntimeSession.from_dict(data)
