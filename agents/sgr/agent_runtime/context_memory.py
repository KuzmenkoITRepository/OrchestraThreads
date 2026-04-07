from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class ContextEntry:
    thread_id: str | None
    entry_type: str
    text: str
    metadata_summary: str | None
    event_id: str | None
    created_at: str


class ContextMemory:
    def __init__(self, max_entries: int = 16) -> None:
        self._entries: deque[ContextEntry] = deque(maxlen=max_entries)

    def add_entry(
        self,
        *,
        thread_id: str | None,
        entry_type: str,
        text: str,
        metadata_summary: str | None = None,
        event_id: str | None = None,
    ) -> None:
        preview = " ".join(str(text).split()).strip()
        if not preview:
            return
        entry = ContextEntry(
            thread_id=thread_id,
            entry_type=entry_type,
            text=preview,
            metadata_summary=metadata_summary,
            event_id=event_id,
            created_at=datetime.now(tz=UTC).isoformat(),
        )
        if self._entries and self._entries[-1] == entry:
            return
        self._entries.append(entry)

    def recent_entries(self, thread_id: str | None, limit: int = 6) -> list[ContextEntry]:
        matching = [
            entry
            for entry in self._entries
            if entry.thread_id == thread_id or entry.thread_id is None
        ]
        return matching[-limit:]

    def clear(self) -> None:
        self._entries.clear()

    def __iter__(self) -> Iterable[ContextEntry]:
        return iter(self._entries)
