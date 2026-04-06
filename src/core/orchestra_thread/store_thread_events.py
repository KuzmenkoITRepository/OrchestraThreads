from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import asyncpg

from core.orchestra_thread.common import THREAD_TERMINAL_STATUSES, normalize_status
from core.orchestra_thread.store_base import row_to_dict


@dataclass(frozen=True)
class AppendEventRequest:
    event_id: str
    thread_id: str
    event_kind: str
    notification_status: str | None
    from_agent_slug: str
    to_agent_slug: str
    message_text: str
    interrupts_runtime: bool
    requires_response: bool
    touch_activity: bool
    update_last_message_sender: bool
    set_thread_status: str | None = None
    set_terminal: bool = False


@dataclass(frozen=True)
class EventInsertRequest:
    event_id: str
    thread_id: str
    next_sequence: int
    event_kind: str
    notification_status: str | None
    from_agent_slug: str
    to_agent_slug: str
    message_text: str
    interrupts_runtime: bool
    requires_response: bool
    touch_activity: bool
    update_last_message_sender: bool
    set_thread_status: str | None
    set_terminal: bool
    now: datetime


class ThreadEventsStoreMixin:
    pool: asyncpg.Pool | None

    async def append_thread_event(
        self,
        *,
        request: AppendEventRequest,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                thread = await conn.fetchrow(
                    """
                    SELECT *
                    FROM threads
                    WHERE thread_id = $1
                    FOR UPDATE
                    """,
                    request.thread_id,
                )
                if thread is None:
                    raise KeyError(f"Unknown thread_id: {request.thread_id}")
                if normalize_status(str(thread["status"] or "")) in THREAD_TERMINAL_STATUSES:
                    raise ValueError(f"Thread {request.thread_id} is already terminal")
                insert_request = self._event_insert_request(thread=thread, request=request)
                event, thread_payload = await self._insert_event_and_update_thread(
                    conn=conn,
                    request=insert_request,
                )
        return row_to_dict(event) or {}, row_to_dict(thread_payload) or {}

    def _event_insert_request(
        self, *, thread: Any, request: AppendEventRequest
    ) -> EventInsertRequest:
        return EventInsertRequest(
            event_id=request.event_id,
            thread_id=request.thread_id,
            next_sequence=int(thread["last_sequence_no"] or 0) + 1,
            event_kind=request.event_kind,
            notification_status=request.notification_status,
            from_agent_slug=request.from_agent_slug,
            to_agent_slug=request.to_agent_slug,
            message_text=request.message_text,
            interrupts_runtime=request.interrupts_runtime,
            requires_response=request.requires_response,
            touch_activity=request.touch_activity,
            update_last_message_sender=request.update_last_message_sender,
            set_thread_status=request.set_thread_status,
            set_terminal=request.set_terminal,
            now=datetime.now(UTC),
        )

    async def _insert_event_and_update_thread(
        self,
        *,
        conn: Any,
        request: EventInsertRequest,
    ) -> tuple[Any, Any]:
        event = await conn.fetchrow(
            """
            INSERT INTO thread_events (
                event_id,
                thread_id,
                sequence_no,
                event_kind,
                notification_status,
                from_agent_slug,
                to_agent_slug,
                message_text,
                interrupts_runtime,
                requires_response,
                pending_delivery,
                delivery_attempt_count,
                next_delivery_attempt_at,
                delivered_at,
                last_delivery_error,
                created_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $9, 0,
                CASE WHEN $9 THEN $11::timestamptz ELSE NULL::timestamptz END,
                NULL,
                NULL,
                $11
            )
            RETURNING *
            """,
            request.event_id,
            request.thread_id,
            request.next_sequence,
            request.event_kind,
            request.notification_status,
            request.from_agent_slug,
            request.to_agent_slug,
            request.message_text,
            request.interrupts_runtime,
            request.requires_response,
            request.now,
        )
        thread_payload = await conn.fetchrow(
            """
            UPDATE threads
            SET updated_at = $1,
                status = COALESCE($2, status),
                last_activity_at = CASE WHEN $3 THEN $1 ELSE last_activity_at END,
                last_message_sender_agent_slug = CASE WHEN $4 THEN $5 ELSE last_message_sender_agent_slug END,
                terminal_at = CASE WHEN $6 THEN COALESCE(terminal_at, $1) ELSE terminal_at END,
                last_sequence_no = $7
            WHERE thread_id = $8
            RETURNING *
            """,
            request.now,
            request.set_thread_status,
            request.touch_activity,
            request.update_last_message_sender,
            request.from_agent_slug,
            request.set_terminal,
            request.next_sequence,
            request.thread_id,
        )
        return event, thread_payload
