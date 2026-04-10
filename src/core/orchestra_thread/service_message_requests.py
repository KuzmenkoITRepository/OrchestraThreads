from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from core.orchestra_thread.common import ServiceError, normalize_text_input

MessageRequest = dict[str, str | None]

BAD_REQUEST_STATUS = 400
FROM_AGENT_SLUG = "from_agent_slug"
TO_AGENT_SLUG = "to_agent_slug"
MESSAGE_TEXT = "message_text"
THREAD_ID = "thread_id"
PARENT_THREAD_ID = "parent_thread_id"
CLIENT_REQUEST_ID = "client_request_id"


@dataclass(frozen=True)
class MessageRequestInput:
    from_agent_slug: str
    to_agent_slug: str
    message_text: str
    thread_id: str | None
    parent_thread_id: str | None
    client_request_id: str


def build_message_request(request_input: MessageRequestInput) -> MessageRequest:
    request = {
        FROM_AGENT_SLUG: str(request_input.from_agent_slug or "").strip(),
        TO_AGENT_SLUG: str(request_input.to_agent_slug or "").strip(),
        MESSAGE_TEXT: normalize_text_input(str(request_input.message_text or "")).strip(),
        THREAD_ID: _optional_text(request_input.thread_id),
        PARENT_THREAD_ID: _optional_text(request_input.parent_thread_id),
        CLIENT_REQUEST_ID: request_input.client_request_id,
    }
    validate_message_request(request=request)
    return request


def validate_message_request(*, request: MessageRequest) -> None:
    from_agent_slug = str(request[FROM_AGENT_SLUG] or "")
    to_agent_slug = str(request[TO_AGENT_SLUG] or "")
    message_text = str(request[MESSAGE_TEXT] or "")
    if not from_agent_slug or not to_agent_slug:
        raise ServiceError(
            BAD_REQUEST_STATUS,
            f"{FROM_AGENT_SLUG} and {TO_AGENT_SLUG} are required",
        )
    if from_agent_slug == to_agent_slug:
        raise ServiceError(BAD_REQUEST_STATUS, "agent cannot send a thread message to itself")
    if not message_text:
        raise ServiceError(BAD_REQUEST_STATUS, f"{MESSAGE_TEXT} is required")


def message_request_context(*, request: MessageRequest) -> MessageRequest:
    thread_id = _optional_text(request.get(THREAD_ID))
    parent_thread_id = _optional_text(request.get(PARENT_THREAD_ID))
    return {
        THREAD_ID: thread_id,
        PARENT_THREAD_ID: parent_thread_id,
        FROM_AGENT_SLUG: str(request[FROM_AGENT_SLUG]),
        TO_AGENT_SLUG: str(request[TO_AGENT_SLUG]),
        MESSAGE_TEXT: str(request[MESSAGE_TEXT]),
        CLIENT_REQUEST_ID: str(request[CLIENT_REQUEST_ID]),
    }


def legacy_message_input(*, kwargs: Mapping[str, object]) -> MessageRequestInput:
    return MessageRequestInput(
        from_agent_slug=str(kwargs.get(FROM_AGENT_SLUG) or ""),
        to_agent_slug=str(kwargs.get(TO_AGENT_SLUG) or ""),
        message_text=str(kwargs.get(MESSAGE_TEXT) or ""),
        thread_id=_optional_text(_string_or_none(kwargs.get(THREAD_ID))),
        parent_thread_id=_optional_text(_string_or_none(kwargs.get(PARENT_THREAD_ID))),
        client_request_id=str(kwargs.get(CLIENT_REQUEST_ID) or ""),
    )


def _optional_text(raw_value: str | None) -> str | None:
    normalized_value = str(raw_value or "").strip()
    if normalized_value:
        return normalized_value
    return None


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
