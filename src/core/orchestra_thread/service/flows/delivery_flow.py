from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING, Any

from core.orchestra_thread import common

if TYPE_CHECKING:
    from core.orchestra_thread.service.runtime import OrchestraThreadsService

logger = logging.getLogger(__name__)


async def _process_pending_events(service: OrchestraThreadsService) -> None:
    async with service._lock:
        pending_events = await service.store.list_due_pending_events(
            now_iso=common.utc_now_iso(),
            limit=16,
        )
    process_tasks = [_process_pending_event_item(service, item=item) for item in pending_events]
    await asyncio.gather(*process_tasks)


async def _process_pending_event_item(
    service: OrchestraThreadsService,
    *,
    item: dict[str, Any],
) -> None:
    event_id = str(item.get("event_id") or "").strip()
    target_agent_slug = str(item.get("to_agent_slug") or "").strip()
    if not event_id or not target_agent_slug:
        return
    callback_url = str(item.get("event_callback_url") or "").strip()
    if not callback_url:
        await _mark_delivery_failed(
            service,
            event_id=event_id,
            error_text=(
                f"target agent {target_agent_slug} is not registered or has no event callback"
            ),
        )
        return
    if not service.store.timestamp_within_lease(
        item.get("agent_last_seen_at"),
        lease_seconds=service.agent_lease_seconds,
    ):
        await _mark_delivery_failed(
            service,
            event_id=event_id,
            error_text=f"target agent {target_agent_slug} is offline",
        )
        return
    await _deliver_pending_event(
        service,
        item=item,
        callback_url=callback_url,
        event_id=event_id,
    )


async def _deliver_pending_event(
    service: OrchestraThreadsService,
    *,
    item: dict[str, Any],
    callback_url: str,
    event_id: str,
) -> None:
    payload = {
        "delivery_id": str(uuid.uuid4()),
        "events": [
            {
                "event_id": item.get("event_id"),
                "thread_id": item.get("thread_id"),
                "root_thread_id": item.get("root_thread_id"),
                "parent_thread_id": item.get("parent_thread_id"),
                "owner_agent_slug": item.get("owner_agent_slug"),
                "sequence_no": item.get("sequence_no"),
                "event_kind": item.get("event_kind"),
                "notification_status": item.get("notification_status"),
                "from_agent_slug": item.get("from_agent_slug"),
                "to_agent_slug": item.get("to_agent_slug"),
                "message_text": item.get("message_text"),
                "interrupts_runtime": bool(item.get("interrupts_runtime")),
                "requires_response": bool(item.get("requires_response")),
                "created_at": item.get("created_at"),
            },
        ],
    }
    try:
        await _post_delivery(service, callback_url=callback_url, payload=payload)
    except Exception as exc:
        logger.warning("event delivery failed for %s: %s", event_id, exc)
        await _mark_delivery_failed(service, event_id=event_id, error_text=str(exc))
        return
    async with service._lock:
        await service.store.mark_event_delivered(event_id=event_id)


async def _post_delivery(
    service: OrchestraThreadsService,
    *,
    callback_url: str,
    payload: dict[str, Any],
) -> None:
    assert service._http_session is not None
    async with service._http_session.post(callback_url, json=payload) as response:
        if response.status >= 400:
            body = await response.text()
            raise RuntimeError(f"HTTP {response.status}: {body}")


async def _mark_delivery_failed(
    service: OrchestraThreadsService,
    *,
    event_id: str,
    error_text: str,
) -> None:
    async with service._lock:
        await service.store.mark_event_failed(
            event_id=event_id,
            error_text=error_text,
            retry_base_seconds=service.retry_base_seconds,
            retry_max_seconds=service.retry_max_seconds,
        )
