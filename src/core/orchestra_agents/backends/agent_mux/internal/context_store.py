from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.orchestra_agents.backends.agent_mux.internal.json_store import (
    read_json_object,
    write_json_object,
)
from core.orchestra_agents.backends.agent_mux.internal.state_paths import (
    RuntimeStatePaths,
    normalize_recent_entries,
    short_context_id,
    utc_now,
)


class RuntimeContextStore:
    def __init__(self, paths: RuntimeStatePaths) -> None:
        self._paths = paths

    def context_snapshot(self) -> dict[str, Any]:
        payload = read_json_object(self._paths.context_file)
        return {
            "context_id": _normalize_optional_text(payload.get("context_id")),
            "previous_context_id": _normalize_optional_text(payload.get("previous_context_id")),
            "context_generation": int(payload.get("context_generation") or 0),
            "updated_at": _normalize_optional_text(payload.get("updated_at")),
            "last_session_id": _normalize_optional_text(payload.get("last_session_id")),
            "last_dispatch_id": _normalize_optional_text(payload.get("last_dispatch_id")),
            "last_event_id": _normalize_optional_text(payload.get("last_event_id")),
            "last_event_kind": _normalize_optional_text(payload.get("last_event_kind")),
            "recent_entries": normalize_recent_entries(payload.get("recent_entries")),
        }

    def ensure_context_id(self, *, fallback_context_id: str, generation: int) -> str:
        payload = read_json_object(self._paths.context_file)
        context_id = str(payload.get("context_id") or "").strip()
        if context_id:
            return context_id
        normalized = str(fallback_context_id or "").strip() or short_context_id()
        self.save_context_id(
            context_id=normalized,
            previous_context_id=None,
            generation=generation,
        )
        return normalized

    def save_context_id(
        self,
        *,
        context_id: str,
        previous_context_id: str | None,
        generation: int,
    ) -> None:
        write_json_object(
            self._paths.context_file,
            {
                "context_id": str(context_id).strip() or short_context_id(),
                "previous_context_id": str(previous_context_id or "").strip() or None,
                "context_generation": int(generation),
                "updated_at": utc_now(),
                "last_session_id": None,
                "last_dispatch_id": None,
                "last_event_id": None,
                "last_event_kind": None,
                "recent_entries": [],
            },
        )

    def append_context_entry(
        self,
        *,
        context_id: str,
        entry: _ContextEntryInput | None = None,
        max_entries: int = 16,
        **legacy_fields: Any,
    ) -> None:
        snapshot = self.context_snapshot()
        if snapshot.get("context_id") != str(context_id or "").strip():
            return
        entry_input = entry or _ContextEntryInput(
            role=str(legacy_fields.get("role") or "note"),
            text=str(legacy_fields.get("text") or ""),
            event_id=_normalize_optional_text(legacy_fields.get("event_id")),
            event_kind=_normalize_optional_text(legacy_fields.get("event_kind")),
            source_agent_slug=_normalize_optional_text(legacy_fields.get("source_agent_slug")),
            metadata_summary=_normalize_optional_text(legacy_fields.get("metadata_summary")),
        )
        built_entry = _context_entry(
            entry=entry_input,
        )
        if built_entry is None:
            return
        entries = list(snapshot.get("recent_entries") or [])
        if entries and _is_duplicate_entry(entries[-1], built_entry):
            return
        entries.append(built_entry)
        snapshot["recent_entries"] = entries[-max(1, int(max_entries)) :]
        _update_snapshot_event_fields(
            snapshot,
            event_id=built_entry.get("event_id"),
            event_kind=built_entry.get("event_kind"),
        )
        snapshot["updated_at"] = utc_now()
        write_json_object(self._paths.context_file, snapshot)

    def remember_dispatch_result(
        self,
        *,
        context_id: str,
        dispatch_id: str | None,
        session_id: str | None,
        event_id: str | None,
        event_kind: str | None,
    ) -> None:
        snapshot = self.context_snapshot()
        if snapshot.get("context_id") != str(context_id or "").strip():
            return
        snapshot["last_dispatch_id"] = str(dispatch_id or "").strip() or None
        snapshot["last_session_id"] = str(session_id or "").strip() or None
        _update_snapshot_event_fields(snapshot, event_id=event_id, event_kind=event_kind)
        snapshot["updated_at"] = utc_now()
        write_json_object(self._paths.context_file, snapshot)


@dataclass(frozen=True)
class _ContextEntryInput:
    role: str
    text: str
    event_id: str | None = None
    event_kind: str | None = None
    source_agent_slug: str | None = None
    metadata_summary: str | None = None


def _normalize_optional_text(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _single_line_preview(value: str | None) -> str:
    return " ".join(str(value or "").split())


def _context_entry(*, entry: _ContextEntryInput) -> dict[str, Any] | None:
    preview = _single_line_preview(entry.text)
    metadata_preview = _single_line_preview(entry.metadata_summary)
    if not preview and not metadata_preview:
        return None
    return {
        "role": _normalize_optional_text(entry.role) or "note",
        "event_id": _normalize_optional_text(entry.event_id),
        "event_kind": _normalize_optional_text(entry.event_kind),
        "source_agent_slug": _normalize_optional_text(entry.source_agent_slug),
        "text_preview": preview[:400] or None,
        "metadata_summary": metadata_preview[:400] or None,
        "recorded_at": utc_now(),
    }


def _is_duplicate_entry(previous: dict[str, Any], entry: dict[str, Any]) -> bool:
    keys = (
        "role",
        "event_id",
        "event_kind",
        "source_agent_slug",
        "text_preview",
        "metadata_summary",
    )
    for key in keys:
        if previous.get(key) != entry.get(key):
            return False
    return True


def _update_snapshot_event_fields(
    snapshot: dict[str, Any],
    *,
    event_id: str | None,
    event_kind: str | None,
) -> None:
    normalized_event_id = _normalize_optional_text(event_id)
    normalized_event_kind = _normalize_optional_text(event_kind)
    snapshot["last_event_id"] = normalized_event_id or snapshot.get("last_event_id")
    snapshot["last_event_kind"] = normalized_event_kind or snapshot.get("last_event_kind")
