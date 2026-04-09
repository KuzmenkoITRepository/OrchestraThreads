from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from core.orchestra_agents.backends.agent_mux.internal import session_resolver as _resolver_mod
from core.orchestra_agents.backends.agent_mux.internal import session_state as _state_mod
from core.orchestra_agents.backends.agent_mux.internal import session_store as _store_mod
from core.orchestra_agents.backends.agent_mux.internal.event_types import NormalizedEvent
from core.orchestra_agents.backends.agent_mux.internal.json_store import (
    read_json_object,
    write_json_object,
)
from core.orchestra_agents.backends.agent_mux.internal.queue_mutations import (
    QueueEntry,
    QueueMutationStore,
)
from core.orchestra_agents.backends.agent_mux.internal.state_paths import (
    RuntimeStatePaths,
    sanitize_fragment,
    utc_now,
)
from core.orchestra_agents.runtime import EventDelivery

Payload = dict[str, Any]
OptionalText = str | None


def _event_id(*, delivery_id: OptionalText, index: int, event_id: OptionalText) -> str:
    normalized = str(event_id or "").strip()
    if normalized:
        return normalized
    return f"{delivery_id or 'delivery'}-{index}"


def _next_queue_id(paths: RuntimeStatePaths, event_id: str) -> str:
    counter = read_json_object(paths.counter_file)
    value = int(counter.get("value") or 0) + 1
    write_json_object(paths.counter_file, {"value": value})
    return f"{value:08d}-{sanitize_fragment(event_id)}"


def _claimable_entry(path: Path) -> tuple[str, Path, Payload]:
    payload = read_json_object(path)
    queue_id = _normalized_queue_id(payload, fallback=path.stem)
    return (queue_id, path, payload)


def _normalized_queue_id(payload: Payload, *, fallback: str) -> str:
    normalized = str(payload.get("queue_id") or "").strip()
    return normalized or fallback


class _DeliveryQueueRecorder:
    def __init__(self, paths: RuntimeStatePaths) -> None:
        self._paths = paths
        self._session_store = _store_mod.SessionStore(paths.root)
        self._session_resolver = _resolver_mod.SessionResolver(self._session_store, paths.root)
        self._handled = read_json_object(paths.handled_file)
        self._queued_event_ids: list[str] = []
        self._duplicate_events = 0

    def queue_delivery(self, delivery: EventDelivery) -> Payload:
        for index, event in enumerate(delivery.events):
            self._queue_event(delivery_id=delivery.delivery_id, event=event, index=index)
        write_json_object(self._paths.handled_file, self._handled)
        return {
            "queued_events": len(self._queued_event_ids),
            "duplicate_events": self._duplicate_events,
            "queued_event_ids": self._queued_event_ids,
        }

    def _queue_event(self, *, delivery_id: OptionalText, event: Any, index: int) -> None:
        event_id = _event_id(delivery_id=delivery_id, index=index, event_id=event.event_id)
        if self._handled.get(event_id):
            self._duplicate_events += 1
            return
        payload = self._queued_payload(delivery_id=delivery_id, event=event, event_id=event_id)
        queue_path = self._paths.queue_dir / f"{payload['queue_id']}.json"
        handled_entry = self._handled_entry(payload=payload, event_kind=event.event_kind)
        write_json_object(queue_path, payload)
        self._handled[event_id] = handled_entry
        self._queued_event_ids.append(event_id)
        self._append_session_event(event=event, event_id=event_id)

    def _append_session_event(self, *, event: Any, event_id: str) -> None:
        raw_payload = event.raw_payload or {}
        routing_key = str(raw_payload.get("processing_key") or "").strip()
        if not routing_key:
            return

        routing = _resolver_mod.RoutingKey(routing_key)  # type: ignore[attr-defined]
        session = self._session_resolver.resolve_or_create_session(routing)
        normalized_event = NormalizedEvent(
            event_id=event_id,
            source=str(event.from_agent_slug or "agent_mux"),
            routing_key=routing_key,
            kind=str(event.event_kind or "message"),
            payload=dict(raw_payload),
            created_at=str(event.created_at or utc_now()),
            interrupt=bool(event.interrupts_runtime),
            priority=10,
            metadata={
                "delivery_id": event.raw_payload.get("delivery_id"),
                "notification_status": event.notification_status,
                "requires_response": event.requires_response,
                "to_agent_slug": event.to_agent_slug,
            },
        )
        session.append_event(normalized_event)
        _state_mod.save_session_state(session, self._paths.root)

    def _queued_payload(
        self,
        *,
        delivery_id: OptionalText,
        event: Any,
        event_id: str,
    ) -> Payload:
        raw_payload = event.raw_payload or {}
        processing_key = str(raw_payload.get("processing_key") or "").strip() or None
        return {
            "queue_id": _next_queue_id(self._paths, event_id),
            "delivery_id": delivery_id,
            "queued_at": utc_now(),
            "event_id": event_id,
            "event_kind": event.event_kind,
            "processing_key": processing_key,
            "payload": event.raw_payload,
            "attempt_count": 0,
        }

    def _handled_entry(self, payload: Payload, event_kind: OptionalText) -> Payload:
        queued_at = payload["queued_at"]
        queue_id = payload["queue_id"]
        processing_key = payload["processing_key"]
        return {
            "queued_at": queued_at,
            "queue_id": queue_id,
            "event_kind": event_kind,
            "processing_key": processing_key,
        }


class RuntimeQueueStore:
    complete_entry: Callable[[QueueEntry], None]
    requeue_entry: Callable[..., None]
    discard_entry: Callable[..., None]
    clear_entries_matching: Callable[..., int]
    clear_all_pending_entries: Callable[[], int]

    def __init__(self, paths: RuntimeStatePaths) -> None:
        self._paths = paths
        self._mutations = QueueMutationStore(
            queue_dir=paths.queue_dir,
            processing_dir=paths.processing_dir,
            failed_dir=paths.failed_dir,
        )
        self.complete_entry = self._mutations.complete_entry
        self.requeue_entry = self._mutations.requeue_entry
        self.discard_entry = self._mutations.discard_entry
        self.clear_entries_matching = self._mutations.clear_entries_matching
        self.clear_all_pending_entries = self._mutations.clear_all_pending_entries

    def queue_delivery(self, delivery: EventDelivery) -> dict[str, Any]:
        result = _DeliveryQueueRecorder(self._paths).queue_delivery(delivery)
        result["queue_size"] = self.queue_size()
        return result

    def queue_size(self) -> int:
        return len(list(self._paths.queue_dir.glob("*.json"))) + len(
            list(self._paths.processing_dir.glob("*.json"))
        )

    def claim_next_entry(self) -> QueueEntry | None:
        candidates = sorted(
            (_claimable_entry(path) for path in self._paths.queue_dir.glob("*.json")),
            key=lambda item: item[0],
        )
        if not candidates:
            return None
        queue_id, source_path, payload = candidates[0]
        target_path = self._paths.processing_dir / source_path.name
        source_path.replace(target_path)
        return QueueEntry(queue_id=queue_id, path=target_path, payload=payload)

    def queued_events_by_kind(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for path in self._paths.queue_dir.glob("*.json"):
            payload = read_json_object(path)
            event_kind = str(payload.get("event_kind") or "").strip() or "_unknown"
            counts[event_kind] = counts.get(event_kind, 0) + 1
        return counts

    def failed_count(self) -> int:
        return len(list(self._paths.failed_dir.glob("*.json")))

    def handled_count(self) -> int:
        return len(read_json_object(self._paths.handled_file))
