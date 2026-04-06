from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.orchestra_agents.agent_mux_runtime.json_store import write_json_object
from core.orchestra_agents.agent_mux_runtime.queue_matcher import QueueEntryMatcher
from core.orchestra_agents.agent_mux_runtime.state_paths import utc_now


@dataclass(frozen=True)
class QueueEntry:
    queue_id: str
    path: Path
    payload: dict[str, Any]

    @property
    def event_id(self) -> str | None:
        return QueueEntryMatcher.normalize_optional_text(self.payload.get("event_id"))

    @property
    def event_kind(self) -> str | None:
        return QueueEntryMatcher.normalize_optional_text(self.payload.get("event_kind"))

    @property
    def processing_key(self) -> str | None:
        return QueueEntryMatcher.normalize_optional_text(self.payload.get("processing_key"))


def _safe_unlink(path: Path) -> bool:
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    return True


def _remove_directory_entries(directory: Path) -> int:
    removed = 0
    for path in list(directory.glob("*.json")):
        if _safe_unlink(path):
            removed += 1
    return removed


class QueueMutationStore:
    def __init__(self, *, queue_dir: Path, processing_dir: Path, failed_dir: Path) -> None:
        self._queue_dir = queue_dir
        self._processing_dir = processing_dir
        self._failed_dir = failed_dir

    def complete_entry(self, entry: QueueEntry) -> None:
        _safe_unlink(entry.path)

    def requeue_entry(self, entry: QueueEntry, *, error_text: str) -> None:
        payload = dict(entry.payload)
        payload["attempt_count"] = int(payload.get("attempt_count") or 0) + 1
        payload["last_error"] = QueueEntryMatcher.normalize_optional_text(error_text)
        payload["requeued_at"] = utc_now()
        target_path = self._queue_dir / entry.path.name
        write_json_object(entry.path, payload)
        entry.path.replace(target_path)

    def discard_entry(self, entry: QueueEntry, *, error_text: str) -> None:
        payload = dict(entry.payload)
        payload["discarded_at"] = utc_now()
        payload["last_error"] = QueueEntryMatcher.normalize_optional_text(error_text)
        write_json_object(entry.path, payload)
        entry.path.replace(self._failed_dir / entry.path.name)

    def clear_entries_matching(self, **fields: str | None) -> int:
        normalized = QueueEntryMatcher.normalize_fields(fields)
        if not normalized:
            return 0
        removed = 0
        for path in list(self._queue_dir.glob("*.json")):
            matches = QueueEntryMatcher.matches_fields(path=path, normalized=normalized)
            if matches and _safe_unlink(path):
                removed += 1
        return removed

    def clear_all_pending_entries(self) -> int:
        return _remove_directory_entries(self._queue_dir) + _remove_directory_entries(
            self._processing_dir
        )
