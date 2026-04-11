from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING, Any

from core.orchestra_thread import common, service_notification_requests, store_thread_events

if TYPE_CHECKING:
    from core.orchestra_thread.service.runtime import OrchestraThreadsService

JsonDict = dict[str, Any]


async def send_notification(
    service: OrchestraThreadsService,
    *,
    request_input: Any | None = None,
    legacy_kwargs: dict[str, object] | None = None,
) -> JsonDict:
    return await _NotificationFlow(service).send_notification(
        request_input=request_input,
        legacy_kwargs=legacy_kwargs,
    )


async def _send_notification_locked(
    service: OrchestraThreadsService,
    *,
    request: dict[str, str],
) -> JsonDict:
    return await _NotificationFlow(service)._send_notification_locked(request=request)


async def _send_notification_with_lock_context(
    service: OrchestraThreadsService,
    notification_context: JsonDict,
) -> JsonDict:
    return await _NotificationFlow(service)._send_notification_with_lock_context(
        notification_context,
    )


async def cascade_close_children(
    service: OrchestraThreadsService,
    *,
    thread_id: str,
    reason: str,
) -> None:
    await _ChildCascadeFlow(service).cascade_close_children(
        thread_id=thread_id,
        reason=reason,
    )


class _NotificationFlow:
    def __init__(self, service: OrchestraThreadsService) -> None:
        self._service = service
        self._cascade = _ChildCascadeFlow(service)
        self._terminal = _TerminalNotificationFlow(service, self._cascade)

    async def send_notification(
        self,
        *,
        request_input: Any | None,
        legacy_kwargs: dict[str, object] | None,
    ) -> JsonDict:
        current_input = request_input
        if current_input is None:
            kwargs = dict(legacy_kwargs or {})
            kwargs.setdefault(
                service_notification_requests.CLIENT_REQUEST_ID,
                str(uuid.uuid4().hex),
            )
            current_input = service_notification_requests.NotificationRequestInput(
                from_agent_slug=str(
                    kwargs.get(service_notification_requests.FROM_AGENT_SLUG) or "",
                ),
                to_agent_slug=str(kwargs.get(service_notification_requests.TO_AGENT_SLUG) or ""),
                thread_id=str(kwargs.get(service_notification_requests.THREAD_ID) or ""),
                status=str(kwargs.get(service_notification_requests.STATUS) or ""),
                message_text=str(
                    kwargs.get(service_notification_requests.MESSAGE_TEXT) or "",
                ),
                client_request_id=str(
                    kwargs.get(service_notification_requests.CLIENT_REQUEST_ID) or "",
                ),
            )
        request = service_notification_requests.build_notification_request(current_input)
        should_notify_stop = bool(request["status"] == "closed")
        response = await self._send_notification_locked(request=request)
        if should_notify_stop:
            await self._terminal.notify_closed_thread(request=request)
        if request["status"] in common.THREAD_TERMINAL_STATUSES:
            await self._terminal.cascade_notification_close(request=request)
        return response

    async def _send_notification_locked(self, *, request: dict[str, str]) -> JsonDict:
        request_context = service_notification_requests.notification_context(request=request)
        async with self._service._lock:
            return await self._send_notification_with_lock_context(request_context)

    async def _send_notification_with_lock_context(
        self,
        notification_context: JsonDict,
    ) -> JsonDict:
        from_agent_slug = str(notification_context["from_agent_slug"])
        cached = await self._service.store.get_idempotent_result(
            from_agent_slug=from_agent_slug,
            client_request_id=str(notification_context["client_request_id"]),
        )
        if cached is not None:
            return cached
        from_agent = await self._service.store.get_agent(from_agent_slug)
        self._service._ensure_peer_allowed(
            from_agent=from_agent,
            from_agent_slug=from_agent_slug,
            to_agent_slug=str(notification_context["to_agent_slug"]),
        )
        thread = await self._notification_thread(notification_context)
        self._validate_notification_actor(thread=thread, notification_context=notification_context)
        response = await self._build_notification_response(notification_context)
        await self._service.store.save_idempotent_result(
            from_agent_slug=str(notification_context["from_agent_slug"]),
            client_request_id=str(notification_context["client_request_id"]),
            operation_name="notification",
            response_payload=response,
        )
        return response

    async def _notification_thread(self, notification_context: JsonDict) -> JsonDict:
        thread = await self._service.store.get_thread(str(notification_context["thread_id"]))
        if thread is None:
            raise common.ServiceError(
                404,
                f"Unknown thread_id: {notification_context['thread_id']}",
            )
        self._service.validate_routing(
            thread=thread,
            from_agent_slug=str(notification_context["from_agent_slug"]),
            to_agent_slug=str(notification_context["to_agent_slug"]),
        )
        return thread

    def _validate_notification_actor(
        self,
        *,
        thread: JsonDict,
        notification_context: JsonDict,
    ) -> None:
        owner_agent_slug = str(thread.get("owner_agent_slug") or "").strip()
        allowed_statuses = self._terminal.allowed_notification_statuses(
            from_agent_slug=str(notification_context["from_agent_slug"]),
            owner_agent_slug=owner_agent_slug,
        )
        status = str(notification_context["status"])
        if status not in allowed_statuses:
            raise common.ServiceError(
                409,
                (
                    f"{notification_context['from_agent_slug']} cannot publish "
                    f"{status} on thread {notification_context['thread_id']}"
                ),
            )

    async def _build_notification_response(self, notification_context: JsonDict) -> JsonDict:
        status = str(notification_context["status"])
        thread_id = str(notification_context["thread_id"])
        event, thread_payload = await self._service.store.append_thread_event(
            request=store_thread_events.AppendEventRequest(
                event_id=str(uuid.uuid4()),
                thread_id=thread_id,
                event_kind="notification",
                notification_status=status,
                from_agent_slug=str(notification_context["from_agent_slug"]),
                to_agent_slug=str(notification_context["to_agent_slug"]),
                message_text=str(notification_context["message_text"]),
                interrupts_runtime=bool(notification_context["requires_delivery"]),
                requires_response=False,
                touch_activity=bool(notification_context["requires_delivery"]),
                update_last_message_sender=False,
                set_thread_status=status,
                set_terminal=bool(notification_context["is_terminal"]),
            ),
        )
        if bool(notification_context["is_terminal"]):
            await self._service.store.cancel_pending_events_for_thread(
                thread_id=thread_id,
                reason=f"thread {thread_id} reached terminal state {status}",
            )
        return {
            "success": True,
            "operation": "notification",
            "thread": self._service.thread_summary(thread_payload),
            "event": event,
        }


class _TerminalNotificationFlow:
    def __init__(
        self,
        service: OrchestraThreadsService,
        cascade_flow: _ChildCascadeFlow,
    ) -> None:
        self._service = service
        self._cascade_flow = cascade_flow

    async def notify_closed_thread(self, *, request: dict[str, str]) -> None:
        await self._service.notify_stop(
            agent_slug=request["to_agent_slug"],
            payload={
                "thread_id": request["thread_id"],
                "reason": f"Thread {request['thread_id']} closed by {request['from_agent_slug']}",
            },
        )

    async def cascade_notification_close(self, *, request: dict[str, str]) -> None:
        await self._cascade_flow.cascade_close_children(
            thread_id=request["thread_id"],
            reason=(
                f"parent thread {request['thread_id']} reached terminal state {request['status']}"
            ),
        )

    @staticmethod
    def allowed_notification_statuses(
        *,
        from_agent_slug: str,
        owner_agent_slug: str,
    ) -> frozenset[str]:
        if from_agent_slug == owner_agent_slug:
            return common.OWNER_NOTIFICATION_STATUSES
        return common.CALLEE_NOTIFICATION_STATUSES


class _ChildCascadeFlow:
    def __init__(self, service: OrchestraThreadsService) -> None:
        self._service = service

    async def cascade_close_children(self, *, thread_id: str, reason: str) -> None:
        child_threads = await self._service.store.list_child_threads(parent_thread_id=thread_id)
        close_tasks = [
            self._close_child_thread(
                child_thread=child_thread,
                parent_thread_id=thread_id,
                reason=reason,
            )
            for child_thread in child_threads
        ]
        await asyncio.gather(*close_tasks)

    async def _close_child_thread(
        self,
        *,
        child_thread: dict[str, Any],
        parent_thread_id: str,
        reason: str,
    ) -> None:
        child_thread_id = str(child_thread.get("thread_id") or "").strip()
        child_status = common.normalize_status(str(child_thread.get("status") or ""))
        if not child_thread_id or child_status in common.THREAD_TERMINAL_STATUSES:
            return
        participants = {
            str(child_thread.get("participant_a_agent_slug") or "").strip(),
            str(child_thread.get("participant_b_agent_slug") or "").strip(),
        }
        notify_tasks = [
            self._service.notify_stop(
                agent_slug=participant,
                payload={
                    "thread_id": child_thread_id,
                    "parent_thread_id": parent_thread_id,
                    "reason": reason,
                },
            )
            for participant in participants
            if participant
        ]
        await asyncio.gather(*notify_tasks)
        async with self._service._lock:
            await self._service.store.update_thread_terminal_status(
                thread_id=child_thread_id,
                status="closed",
            )
            await self._service.store.cancel_pending_events_for_thread(
                thread_id=child_thread_id,
                reason=(f"thread {child_thread_id} closed because ancestor thread became terminal"),
            )
        await self.cascade_close_children(
            thread_id=child_thread_id,
            reason=f"ancestor thread {parent_thread_id} closed descendant {child_thread_id}",
        )
