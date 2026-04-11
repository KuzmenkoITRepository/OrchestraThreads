from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING, Any

from core.orchestra_thread import store_thread_events

if TYPE_CHECKING:
    from core.orchestra_thread.service.runtime import OrchestraThreadsService


async def _process_inactivity_candidates(service: OrchestraThreadsService) -> None:
    async with service._lock:
        candidates = await service.store.list_inactivity_candidates(
            timeout_seconds=service.inactivity_timeout_seconds,
            limit=32,
        )
    inactivity_tasks = [_build_inactivity_task(service, thread=thread) for thread in candidates]
    await asyncio.gather(*inactivity_tasks)


async def _build_inactivity_task(
    service: OrchestraThreadsService,
    *,
    thread: dict[str, Any],
) -> None:
    thread_id = str(thread.get("thread_id") or "").strip()
    recipient = str(thread.get("last_message_sender_agent_slug") or "").strip()
    last_activity_at = str(thread.get("last_activity_at") or "").strip()
    if not thread_id or not recipient:
        return
    message = (
        f"Thread {thread_id} has no new activity for at least "
        f"{service.inactivity_timeout_seconds} seconds since {last_activity_at}. "
        "You may resume it with a new message or close it."
    )
    await _append_inactivity_event(
        service,
        thread_id=thread_id,
        recipient=recipient,
        message=message,
    )


async def _append_inactivity_event(
    service: OrchestraThreadsService,
    *,
    thread_id: str,
    recipient: str,
    message: str,
) -> None:
    async with service._lock:
        await service.store.append_thread_event(
            request=store_thread_events.AppendEventRequest(
                event_id=str(uuid.uuid4()),
                thread_id=thread_id,
                event_kind="inactive",
                notification_status=None,
                from_agent_slug="orchestra_threads",
                to_agent_slug=recipient,
                message_text=message,
                interrupts_runtime=True,
                requires_response=False,
                touch_activity=False,
                update_last_message_sender=False,
            ),
        )
        await service.store.mark_inactivity_sent(thread_id=thread_id)
