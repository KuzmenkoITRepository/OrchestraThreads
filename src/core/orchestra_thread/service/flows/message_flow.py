from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from core.orchestra_thread import (
    common,
    service_message_requests,
    store_thread_creation,
    store_thread_events,
)

if TYPE_CHECKING:
    from core.orchestra_thread.service.runtime import OrchestraThreadsService

JsonDict = dict[str, Any]


async def send_message(
    service: OrchestraThreadsService,
    *,
    request_input: Any | None = None,
    legacy_kwargs: dict[str, object] | None = None,
) -> JsonDict:
    return await _MessageFlow(service).send_message(
        request_input=request_input,
        legacy_kwargs=legacy_kwargs,
    )


async def _send_message_locked(
    service: OrchestraThreadsService,
    *,
    request: dict[str, str | None],
) -> JsonDict:
    return await _MessageFlow(service)._send_message_locked(request=request)


async def _send_message_with_lock_context(
    service: OrchestraThreadsService,
    message_request_context: JsonDict,
) -> JsonDict:
    return await _MessageFlow(service)._send_message_with_lock_context(message_request_context)


class _MessageFlow:
    def __init__(self, service: OrchestraThreadsService) -> None:
        self._service = service
        self._resolver = _MessageThreadResolver(service)

    async def send_message(
        self,
        *,
        request_input: Any | None,
        legacy_kwargs: dict[str, object] | None,
    ) -> JsonDict:
        current_input = request_input
        if current_input is None:
            kwargs = dict(legacy_kwargs or {})
            kwargs.setdefault(service_message_requests.CLIENT_REQUEST_ID, str(uuid.uuid4().hex))
            current_input = _legacy_message_input(kwargs)
        request = service_message_requests.build_message_request(current_input)
        return await self._send_message_locked(request=request)

    async def _send_message_locked(self, *, request: dict[str, str | None]) -> JsonDict:
        message_context = service_message_requests.message_request_context(request=request)
        async with self._service._lock:
            return await self._send_message_with_lock_context(message_context)

    async def _send_message_with_lock_context(
        self,
        message_request_context: JsonDict,
    ) -> JsonDict:
        from_agent_slug = str(message_request_context["from_agent_slug"])
        to_agent_slug = str(message_request_context["to_agent_slug"])
        from_agent = await self._service.store.get_agent(from_agent_slug)
        self._service._ensure_peer_allowed(
            from_agent=from_agent,
            from_agent_slug=from_agent_slug,
            to_agent_slug=to_agent_slug,
        )
        cached = await self._service.store.get_idempotent_result(
            from_agent_slug=from_agent_slug,
            client_request_id=str(message_request_context["client_request_id"]),
        )
        if cached is not None:
            return cached
        response = await self._build_message_response(message_request_context)
        await self._service.store.save_idempotent_result(
            from_agent_slug=str(message_request_context["from_agent_slug"]),
            client_request_id=str(message_request_context["client_request_id"]),
            operation_name="message",
            response_payload=response,
        )
        return response

    async def _build_message_response(self, message_request_context: JsonDict) -> JsonDict:
        thread, created_thread = await self._resolver.resolve_message_thread(
            thread_id=str(message_request_context.get("thread_id") or "").strip() or None,
            parent_thread_id=str(message_request_context.get("parent_thread_id") or "").strip()
            or None,
            from_agent_slug=str(message_request_context["from_agent_slug"]),
            to_agent_slug=str(message_request_context["to_agent_slug"]),
        )
        event, thread_payload = await self._service.store.append_thread_event(
            request=store_thread_events.AppendEventRequest(
                event_id=str(uuid.uuid4()),
                thread_id=str(thread.get("thread_id")),
                event_kind="message",
                notification_status=None,
                from_agent_slug=str(message_request_context["from_agent_slug"]),
                to_agent_slug=str(message_request_context["to_agent_slug"]),
                message_text=str(message_request_context["message_text"]),
                interrupts_runtime=True,
                requires_response=True,
                touch_activity=True,
                update_last_message_sender=True,
                set_thread_status="open",
            ),
        )
        return {
            "success": True,
            "operation": "message",
            "created_thread": created_thread,
            "thread": self._service.thread_summary(thread_payload),
            "event": event,
        }


class _MessageThreadResolver:
    def __init__(self, service: OrchestraThreadsService) -> None:
        self._service = service

    async def resolve_message_thread(
        self,
        *,
        thread_id: str | None,
        parent_thread_id: str | None,
        from_agent_slug: str,
        to_agent_slug: str,
    ) -> tuple[JsonDict, bool]:
        if thread_id:
            return await self._resolve_existing_thread(
                thread_id=thread_id,
                from_agent_slug=from_agent_slug,
                to_agent_slug=to_agent_slug,
            )
        if parent_thread_id:
            return await self._resolve_child_thread(
                parent_thread_id=parent_thread_id,
                from_agent_slug=from_agent_slug,
                to_agent_slug=to_agent_slug,
            )
        return await self._service.store.get_or_create_root_thread(
            request=store_thread_creation.RootThreadRequest(
                thread_id=str(uuid.uuid4()),
                owner_agent_slug=from_agent_slug,
                from_agent_slug=from_agent_slug,
                to_agent_slug=to_agent_slug,
            ),
        )

    async def _resolve_existing_thread(
        self,
        *,
        thread_id: str,
        from_agent_slug: str,
        to_agent_slug: str,
    ) -> tuple[JsonDict, bool]:
        thread = await self._service.store.get_thread(thread_id)
        if thread is None:
            raise common.ServiceError(404, f"Unknown thread_id: {thread_id}")
        self._service.validate_routing(
            thread=thread,
            from_agent_slug=from_agent_slug,
            to_agent_slug=to_agent_slug,
        )
        return thread, False

    async def _resolve_child_thread(
        self,
        *,
        parent_thread_id: str,
        from_agent_slug: str,
        to_agent_slug: str,
    ) -> tuple[JsonDict, bool]:
        parent_thread = await self._service.store.get_thread(parent_thread_id)
        if parent_thread is None:
            raise common.ServiceError(404, f"Unknown parent_thread_id: {parent_thread_id}")
        parent_status = common.normalize_status(str(parent_thread.get("status") or ""))
        if parent_status in common.THREAD_TERMINAL_STATUSES:
            raise common.ServiceError(409, f"Parent thread {parent_thread_id} is already terminal")
        self._service.thread_peer_agent_slug(thread=parent_thread, agent_slug=from_agent_slug)
        return await self._service.store.get_or_create_child_thread(
            request=store_thread_creation.ChildThreadRequest(
                thread_id=str(uuid.uuid4()),
                root_thread_id=str(parent_thread.get("root_thread_id")),
                parent_thread_id=parent_thread_id,
                owner_agent_slug=from_agent_slug,
                from_agent_slug=from_agent_slug,
                to_agent_slug=to_agent_slug,
            ),
        )


def _legacy_message_input(kwargs: dict[str, object]) -> Any:
    return service_message_requests.MessageRequestInput(
        from_agent_slug=str(kwargs.get(service_message_requests.FROM_AGENT_SLUG) or ""),
        to_agent_slug=str(kwargs.get(service_message_requests.TO_AGENT_SLUG) or ""),
        message_text=str(kwargs.get(service_message_requests.MESSAGE_TEXT) or ""),
        thread_id=_optional_legacy_text(kwargs.get(service_message_requests.THREAD_ID)),
        parent_thread_id=_optional_legacy_text(
            kwargs.get(service_message_requests.PARENT_THREAD_ID),
        ),
        client_request_id=str(kwargs.get(service_message_requests.CLIENT_REQUEST_ID) or ""),
    )


def _optional_legacy_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if normalized:
        return normalized
    return None
