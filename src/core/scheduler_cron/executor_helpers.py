from __future__ import annotations

import json
import uuid

DEFAULT_EVENT_KIND = "message"
DEFAULT_SCHEDULER_AGENT = "sgr"
SCHEDULER_SOURCE = "scheduler_cron"


def required_str(raw_value: object, *, field: str) -> str:
    if isinstance(raw_value, str) and raw_value.strip():
        return raw_value.strip()
    raise ValueError(f"{field} is required")


def as_dict(raw_value: object) -> dict[str, object]:
    return dict(raw_value) if isinstance(raw_value, dict) else {}


def render_json(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def event_kind_from(payload: dict[str, object]) -> str:
    raw = str(payload.get("event_kind") or DEFAULT_EVENT_KIND).strip()
    return raw or DEFAULT_EVENT_KIND


def scheduler_target(raw_value: object) -> str:
    if raw_value is None:
        return DEFAULT_SCHEDULER_AGENT
    return required_str(raw_value, field="target_agent")


def dict_response(raw_value: object) -> dict[str, object]:
    return dict(raw_value) if isinstance(raw_value, dict) else {"ok": True}


def delivery_payload(
    *,
    agent_slug: str,
    event_kind: str,
    message_text: str,
    requires_response: bool,
) -> dict[str, object]:
    event_uuid = uuid.uuid4().hex
    event_id = f"scheduler-{event_uuid}"
    event_item = {
        "event_id": event_id,
        "event_kind": event_kind,
        "from_agent_slug": SCHEDULER_SOURCE,
        "to_agent_slug": agent_slug,
        "message_text": message_text,
        "requires_response": requires_response,
    }
    return {
        "agent_slug": agent_slug,
        "event_data": {
            "delivery_id": event_id,
            "events": [event_item],
        },
    }
