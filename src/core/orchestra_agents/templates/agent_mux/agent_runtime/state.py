"""Durable local state helpers for the generic agent_mux runtime."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from core.orchestra_agents.runtime import EventDelivery


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_fragment(value: str) -> str:
    text = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in str(value or "").strip())
    return text.strip("._") or "item"


def _short_context_id() -> str:
    return uuid.uuid4().hex[:12]


def _normalize_recent_entries(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    entries: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        entries.append({str(key): item[key] for key in item.keys()})
    return entries


@dataclass(frozen=True)
class QueueEntry:
    queue_id: str
    path: Path
    payload: dict[str, Any]

    @property
    def event_id(self) -> Optional[str]:
        normalized = str(self.payload.get("event_id") or "").strip()
        return normalized or None

    @property
    def event_kind(self) -> Optional[str]:
        normalized = str(self.payload.get("event_kind") or "").strip()
        return normalized or None

    @property
    def processing_key(self) -> Optional[str]:
        normalized = str(self.payload.get("processing_key") or "").strip()
        return normalized or None


class AgentMuxRuntimeState:
    """Small file-backed state store for accepted deliveries and worker runs."""

    def __init__(self, root_dir: str) -> None:
        self.root = Path(root_dir).expanduser().resolve()
        self.queue_dir = self.root / "queue"
        self.processing_dir = self.root / "processing"
        self.failed_dir = self.root / "failed"
        self.artifacts_dir = self.root / "artifacts"
        self.meta_dir = self.root / "meta"
        self.home_dir = self.root / "home"
        self.active_context_path = self.root / "active_context.json"
        self.handled_file = self.meta_dir / "handled_events.json"
        self.active_file = self.meta_dir / "active_dispatches.json"
        self.counter_file = self.meta_dir / "queue_counter.json"
        self.context_file = self.meta_dir / "context.json"

    @property
    def root_dir(self) -> str:
        return str(self.root)

    def ensure_layout(self) -> None:
        for path in (
            self.root,
            self.queue_dir,
            self.processing_dir,
            self.failed_dir,
            self.artifacts_dir,
            self.meta_dir,
            self.home_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
        if not self.handled_file.exists():
            self._write_json_object(self.handled_file, {})
        if not self.active_file.exists():
            self._write_json_object(self.active_file, {})
        if not self.counter_file.exists():
            self._write_json_object(self.counter_file, {"value": 0})
        if not self.context_file.exists():
            self._write_json_object(self.context_file, {})

    def _read_json_object(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _write_json_object(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f".{path.name}.tmp")
        temp_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True),
            encoding="utf-8",
        )
        temp_path.replace(path)

    def _next_queue_counter(self) -> int:
        counter = self._read_json_object(self.counter_file)
        value = int(counter.get("value") or 0) + 1
        self._write_json_object(self.counter_file, {"value": value})
        return value

    def queue_delivery(self, delivery: EventDelivery) -> dict[str, Any]:
        self.ensure_layout()
        handled = self._read_json_object(self.handled_file)
        queued_event_ids: list[str] = []
        duplicate_events = 0

        for index, event in enumerate(delivery.events):
            event_id = str(event.event_id or "").strip() or f"{delivery.delivery_id or 'delivery'}-{index}"
            if handled.get(event_id):
                duplicate_events += 1
                continue
            queue_counter = self._next_queue_counter()
            queue_id = f"{queue_counter:08d}-{_sanitize_fragment(event_id)}"
            queue_path = self.queue_dir / f"{queue_id}.json"
            processing_key = str((event.raw_payload or {}).get("processing_key") or "").strip() or None
            payload = {
                "queue_id": queue_id,
                "delivery_id": delivery.delivery_id,
                "queued_at": _utc_now(),
                "event_id": event_id,
                "event_kind": event.event_kind,
                "processing_key": processing_key,
                "payload": event.raw_payload,
                "attempt_count": 0,
            }
            self._write_json_object(queue_path, payload)
            handled[event_id] = {
                "queued_at": payload["queued_at"],
                "queue_id": queue_id,
                "event_kind": event.event_kind,
                "processing_key": processing_key,
            }
            queued_event_ids.append(event_id)

        self._write_json_object(self.handled_file, handled)
        return {
            "queued_events": len(queued_event_ids),
            "duplicate_events": duplicate_events,
            "queued_event_ids": queued_event_ids,
            "queue_size": self.queue_size(),
        }

    def queue_size(self) -> int:
        self.ensure_layout()
        return sum(1 for _ in self.queue_dir.glob("*.json")) + sum(1 for _ in self.processing_dir.glob("*.json"))

    def context_snapshot(self) -> dict[str, Any]:
        self.ensure_layout()
        payload = self._read_json_object(self.context_file)
        return {
            "context_id": str(payload.get("context_id") or "").strip() or None,
            "previous_context_id": str(payload.get("previous_context_id") or "").strip() or None,
            "context_generation": int(payload.get("context_generation") or 0),
            "updated_at": str(payload.get("updated_at") or "").strip() or None,
            "last_session_id": str(payload.get("last_session_id") or "").strip() or None,
            "last_dispatch_id": str(payload.get("last_dispatch_id") or "").strip() or None,
            "last_event_id": str(payload.get("last_event_id") or "").strip() or None,
            "last_event_kind": str(payload.get("last_event_kind") or "").strip() or None,
            "recent_entries": _normalize_recent_entries(payload.get("recent_entries")),
        }

    def ensure_context_id(self, *, fallback_context_id: str, generation: int) -> str:
        self.ensure_layout()
        payload = self._read_json_object(self.context_file)
        context_id = str(payload.get("context_id") or "").strip()
        if context_id:
            return context_id
        normalized = str(fallback_context_id or "").strip() or _short_context_id()
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
        previous_context_id: Optional[str],
        generation: int,
    ) -> None:
        self.ensure_layout()
        self._write_json_object(
            self.context_file,
            {
                "context_id": str(context_id).strip() or _short_context_id(),
                "previous_context_id": str(previous_context_id or "").strip() or None,
                "context_generation": int(generation),
                "updated_at": _utc_now(),
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
        role: str,
        text: str,
        event_id: Optional[str] = None,
        event_kind: Optional[str] = None,
        source_agent_slug: Optional[str] = None,
        metadata_summary: Optional[str] = None,
        max_entries: int = 16,
    ) -> None:
        self.ensure_layout()
        snapshot = self.context_snapshot()
        if snapshot.get("context_id") != str(context_id or "").strip():
            return
        preview = " ".join(str(text or "").split())
        metadata_preview = " ".join(str(metadata_summary or "").split())
        if not preview and not metadata_preview:
            return
        entries = list(snapshot.get("recent_entries") or [])
        entry = {
            "role": str(role or "note").strip() or "note",
            "event_id": str(event_id or "").strip() or None,
            "event_kind": str(event_kind or "").strip() or None,
            "source_agent_slug": str(source_agent_slug or "").strip() or None,
            "text_preview": preview[:400] or None,
            "metadata_summary": metadata_preview[:400] or None,
            "recorded_at": _utc_now(),
        }
        if entries:
            previous = entries[-1]
            duplicate = True
            for key in ("role", "event_id", "event_kind", "source_agent_slug", "text_preview", "metadata_summary"):
                if previous.get(key) != entry.get(key):
                    duplicate = False
                    break
            if duplicate:
                return
        entries.append(entry)
        snapshot["recent_entries"] = entries[-max(1, int(max_entries)) :]
        snapshot["last_event_id"] = str(event_id or "").strip() or snapshot.get("last_event_id")
        snapshot["last_event_kind"] = str(event_kind or "").strip() or snapshot.get("last_event_kind")
        snapshot["updated_at"] = _utc_now()
        self._write_json_object(self.context_file, snapshot)

    def remember_dispatch_result(
        self,
        *,
        context_id: str,
        dispatch_id: Optional[str],
        session_id: Optional[str],
        event_id: Optional[str],
        event_kind: Optional[str],
    ) -> None:
        self.ensure_layout()
        snapshot = self.context_snapshot()
        if snapshot.get("context_id") != str(context_id or "").strip():
            return
        snapshot["last_dispatch_id"] = str(dispatch_id or "").strip() or None
        snapshot["last_session_id"] = str(session_id or "").strip() or None
        snapshot["last_event_id"] = str(event_id or "").strip() or snapshot.get("last_event_id")
        snapshot["last_event_kind"] = str(event_kind or "").strip() or snapshot.get("last_event_kind")
        snapshot["updated_at"] = _utc_now()
        self._write_json_object(self.context_file, snapshot)

    def claim_next_entry(self) -> Optional[QueueEntry]:
        self.ensure_layout()
        candidates: list[tuple[str, Path, dict[str, Any]]] = []
        for path in self.queue_dir.glob("*.json"):
            payload = self._read_json_object(path)
            queue_id = str(payload.get("queue_id") or path.stem).strip() or path.stem
            candidates.append((queue_id, path, payload))
        if not candidates:
            return None
        _, source_path, payload = sorted(candidates, key=lambda item: item[0])[0]
        queue_id = str(payload.get("queue_id") or source_path.stem).strip() or source_path.stem
        target_path = self.processing_dir / source_path.name
        source_path.replace(target_path)
        return QueueEntry(queue_id=queue_id, path=target_path, payload=payload)

    def complete_entry(self, entry: QueueEntry) -> None:
        try:
            entry.path.unlink()
        except FileNotFoundError:
            return

    def requeue_entry(self, entry: QueueEntry, *, error_text: str) -> None:
        payload = dict(entry.payload)
        payload["attempt_count"] = int(payload.get("attempt_count") or 0) + 1
        payload["last_error"] = str(error_text or "").strip() or None
        payload["requeued_at"] = _utc_now()
        target_path = self.queue_dir / entry.path.name
        self._write_json_object(entry.path, payload)
        entry.path.replace(target_path)

    def discard_entry(self, entry: QueueEntry, *, error_text: str) -> None:
        payload = dict(entry.payload)
        payload["discarded_at"] = _utc_now()
        payload["last_error"] = str(error_text or "").strip() or None
        self._write_json_object(entry.path, payload)
        target_path = self.failed_dir / entry.path.name
        entry.path.replace(target_path)

    def clear_entries_matching(self, **fields: Optional[str]) -> int:
        self.ensure_layout()
        normalized = {
            key: str(value).strip()
            for key, value in fields.items()
            if str(value or "").strip()
        }
        if not normalized:
            return 0
        removed = 0
        for path in list(self.queue_dir.glob("*.json")):
            payload = self._read_json_object(path)
            raw_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
            matched = True
            for key, value in normalized.items():
                candidate = str(raw_payload.get(key) or payload.get(key) or "").strip()
                if candidate != value:
                    matched = False
                    break
            if not matched:
                continue
            try:
                path.unlink()
                removed += 1
            except FileNotFoundError:
                continue
        return removed

    def clear_all_pending_entries(self) -> int:
        self.ensure_layout()
        removed = 0
        for directory in (self.queue_dir, self.processing_dir):
            for path in list(directory.glob("*.json")):
                try:
                    path.unlink()
                    removed += 1
                except FileNotFoundError:
                    continue
        return removed

    def remember_active_dispatch(
        self,
        *,
        dispatch_id: str,
        event_id: Optional[str],
        event_kind: Optional[str],
        artifact_dir: str | None = None,
        queue_id: str | None = None,
    ) -> None:
        self.ensure_layout()
        active = self._read_json_object(self.active_file)
        active[str(dispatch_id).strip()] = {
            "event_id": str(event_id or "").strip() or None,
            "event_kind": str(event_kind or "").strip() or None,
            "artifact_dir": str(artifact_dir or "").strip() or None,
            "queue_id": str(queue_id or "").strip() or None,
            "updated_at": _utc_now(),
        }
        self._write_json_object(self.active_file, active)

    def clear_active_dispatch(self, dispatch_id: str) -> None:
        self.ensure_layout()
        active = self._read_json_object(self.active_file)
        active.pop(str(dispatch_id or "").strip(), None)
        self._write_json_object(self.active_file, active)

    def reset_runtime_metadata(self) -> None:
        self.ensure_layout()
        self._write_json_object(self.active_file, {})

    def artifact_dir_for_dispatch(self, dispatch_id: str) -> Path:
        self.ensure_layout()
        return self.artifacts_dir / _sanitize_fragment(dispatch_id)

    def codex_home_dir(self) -> Path:
        self.ensure_layout()
        return self.home_dir

    def status_snapshot(self) -> dict[str, Any]:
        self.ensure_layout()
        active = self._read_json_object(self.active_file)
        handled = self._read_json_object(self.handled_file)
        queued_by_kind: dict[str, int] = {}
        for path in self.queue_dir.glob("*.json"):
            payload = self._read_json_object(path)
            event_kind = str(payload.get("event_kind") or "").strip() or "_unknown"
            queued_by_kind[event_kind] = queued_by_kind.get(event_kind, 0) + 1
        failed_count = sum(1 for _ in self.failed_dir.glob("*.json"))
        return {
            "runtime_state_root": self.root_dir,
            "context": self.context_snapshot(),
            "queue_size": self.queue_size(),
            "queued_events_by_kind": queued_by_kind,
            "failed_queue_size": failed_count,
            "active_dispatches": active,
            "active_dispatch_count": len(active),
            "handled_event_count": len(handled),
            "active_context_path": str(self.active_context_path),
        }
