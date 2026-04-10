from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from core.orchestra_thread.common import (
    DELIVERED_NOTIFICATION_STATUSES,
    THREAD_NOTIFICATION_STATUSES,
    THREAD_TERMINAL_STATUSES,
    ServiceError,
    normalize_status,
    normalize_text_input,
)

BAD_REQUEST_STATUS = 400
FROM_AGENT_SLUG = "from_agent_slug"
TO_AGENT_SLUG = "to_agent_slug"
THREAD_ID = "thread_id"
STATUS = "status"
MESSAGE_TEXT = "message_text"
CLIENT_REQUEST_ID = "client_request_id"


@dataclass(frozen=True)
class NotificationRequestInput:
    from_agent_slug: str
    to_agent_slug: str
    thread_id: str
    status: str
    message_text: str
    client_request_id: str


def build_notification_request(request_input: NotificationRequestInput) -> dict[str, str]:
    request = {
        FROM_AGENT_SLUG: str(request_input.from_agent_slug or "").strip(),
        TO_AGENT_SLUG: str(request_input.to_agent_slug or "").strip(),
        THREAD_ID: str(request_input.thread_id or "").strip(),
        STATUS: normalize_status(request_input.status),
        MESSAGE_TEXT: normalize_text_input(str(request_input.message_text or "")).strip(),
        CLIENT_REQUEST_ID: request_input.client_request_id,
    }
    validate_notification_request(request=request)
    return request


def validate_notification_request(*, request: dict[str, str]) -> None:
    if not request[FROM_AGENT_SLUG] or not request[TO_AGENT_SLUG] or not request[THREAD_ID]:
        raise ServiceError(
            BAD_REQUEST_STATUS,
            f"{FROM_AGENT_SLUG}, {TO_AGENT_SLUG}, and {THREAD_ID} are required",
        )
    if request[STATUS] not in THREAD_NOTIFICATION_STATUSES:
        raise ServiceError(
            BAD_REQUEST_STATUS,
            f"Unsupported notification status: {request[STATUS]}",
        )
    if not request[MESSAGE_TEXT]:
        raise ServiceError(BAD_REQUEST_STATUS, f"{MESSAGE_TEXT} is required")


def notification_context(*, request: dict[str, str]) -> dict[str, Any]:
    notification_status = request[STATUS]
    return {
        THREAD_ID: request[THREAD_ID],
        FROM_AGENT_SLUG: request[FROM_AGENT_SLUG],
        TO_AGENT_SLUG: request[TO_AGENT_SLUG],
        STATUS: notification_status,
        MESSAGE_TEXT: request[MESSAGE_TEXT],
        "requires_delivery": notification_status in DELIVERED_NOTIFICATION_STATUSES,
        "is_terminal": notification_status in THREAD_TERMINAL_STATUSES,
        CLIENT_REQUEST_ID: request[CLIENT_REQUEST_ID],
    }


def legacy_notification_input(*, kwargs: Mapping[str, object]) -> NotificationRequestInput:
    return NotificationRequestInput(
        from_agent_slug=str(kwargs.get(FROM_AGENT_SLUG) or ""),
        to_agent_slug=str(kwargs.get(TO_AGENT_SLUG) or ""),
        thread_id=str(kwargs.get(THREAD_ID) or ""),
        status=str(kwargs.get(STATUS) or ""),
        message_text=str(kwargs.get(MESSAGE_TEXT) or ""),
        client_request_id=str(kwargs.get(CLIENT_REQUEST_ID) or ""),
    )
