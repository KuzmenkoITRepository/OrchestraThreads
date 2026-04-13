"""Regression test: ensure message payload uses configured target agent slug."""

from core.telegram_events.service_event_payload import build_message_event_payload


def test_message_uses_configured_agent_slug() -> None:
    """Message event payload should respect target_agent_slug parameter.

    Regression test: service_event_payload.py hardcoded _SECRETARY_AGENT = "secretary"
    which breaks configurable agent routing. This test ensures the fix works.
    """
    message_data = {
        "message_id": 42,
        "sender_id": 7,
        "sender_name": "Bob",
        "chat_id": 321,
        "chat_name": "Test Chat",
        "text": "Hello",
        "timestamp": "2024-01-01T12:00:00Z",
    }

    # Test with non-default slug
    event_data = build_message_event_payload(message_data, target_agent_slug="assistant-alpha")

    assert len(event_data["events"]) == 1
    event = event_data["events"][0]
    assert event["to_agent_slug"] == "assistant-alpha"


def test_message_payload_defaults_to_secretary() -> None:
    """Message event payload should default to secretary for backwards compatibility."""
    message_data = {
        "message_id": 43,
        "sender_id": 8,
        "sender_name": "Alice",
        "chat_id": 322,
        "chat_name": "Another Chat",
        "text": "Test",
        "timestamp": "2024-01-01T13:00:00Z",
    }

    event_data = build_message_event_payload(message_data)

    assert len(event_data["events"]) == 1
    event = event_data["events"][0]
    assert event["to_agent_slug"] == "secretary"
