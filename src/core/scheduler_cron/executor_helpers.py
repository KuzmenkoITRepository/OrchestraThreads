from __future__ import annotations

import json
import uuid

DEFAULT_EVENT_KIND = "message"
DEFAULT_SCHEDULER_AGENT = "sgr"
SCHEDULER_SOURCE = "scheduler_cron"


def required_str(value: object, *, field: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ValueError(f"{field} is required")


def as_dict(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def render_json(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def event_kind_from(payload: dict[str, object]) -> str:
    raw = str(payload.get("event_kind") or DEFAULT_EVENT_KIND).strip()
    return raw or DEFAULT_EVENT_KIND


def scheduler_target(value: object) -> str:
    if value is None:
        return DEFAULT_SCHEDULER_AGENT
    return required_str(value, field="target_agent")


def dict_response(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {"ok": True}


def delivery_payload(
    *,
    agent_slug: str,
    event_kind: str,
    message_text: str,
    requires_response: bool,
) -> dict[str, object]:
    event_id = f"scheduler-{uuid.uuid4().hex}"
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
