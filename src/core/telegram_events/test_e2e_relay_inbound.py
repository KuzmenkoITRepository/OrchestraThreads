"""Inbound pytest E2E coverage for Telegram relay integration."""

from __future__ import annotations

import asyncio
from typing import Any

from core.telegram_events import sse_consumer
from core.telegram_events.conftest import open_telegram_events_context


def build_test_sse_event() -> dict[str, Any]:
    """Build a test SSE event for parsing tests."""
    return {
        "event_id": "evt-123",
        "event_type": "message",
        "occurred_at": "2024-01-01T12:00:00Z",
        "mode": "private",
        "account": "my_account",
        "update": {
            "message": {
                "id": 42,
                "from": {"id": 999, "first_name": "Bob"},
                "chat": {"id": 888, "title": "Private"},
                "text": "Test message",
                "date": 1704067200,
            }
        },
    }


class _StopAfterFirstEventCollector:
    """Collect the first SSE event and stop the consumer."""

    def __init__(self) -> None:
        self.events: list[Any] = []
        self.consumer: sse_consumer.SSEConsumer | None = None

    async def __call__(self, event: Any) -> None:
        self.events.append(event)
        if self.consumer is not None:
            await self.consumer.stop()


async def _collect_event_from_context(
    telegram_events_context: dict[str, Any],
    event_data: dict[str, Any],
) -> Any:
    """Load one SSE event into the relay and return the first collected event."""
    telegram_events_context["fake_relay"].sse_events = [event_data]
    collector = _StopAfterFirstEventCollector()
    consumer = sse_consumer.SSEConsumer(
        events_url=str(telegram_events_context["relay_server"].make_url("/events/telegram")),
        bearer_token=telegram_events_context["bearer_token"],
        on_event=collector,
    )
    collector.consumer = consumer
    await consumer.start()
    await asyncio.sleep(0.1)
    await consumer.stop()
    assert len(collector.events) == 1
    return collector.events[0]


async def test_sse_consumer_connects_with_bearer_auth() -> None:
    """Connect to the relay SSE stream with bearer authentication."""
    async with open_telegram_events_context() as telegram_events_context:
        event = await _collect_event_from_context(
            telegram_events_context,
            {
                "event_id": "test-1",
                "event_type": "message",
                "occurred_at": "2024-01-01T00:00:00Z",
                "mode": "group",
                "account": "test_account",
                "update": {
                    "message": {
                        "id": 100,
                        "from": {"id": 200, "first_name": "Alice"},
                        "chat": {"id": 300, "title": "Test Chat"},
                        "text": "Hello world",
                        "date": 1704067200,
                    }
                },
            },
        )
        assert event.event_id == "test-1"


async def test_sse_event_parsing() -> None:
    """Parse relay SSE payloads into consumer event objects."""
    async with open_telegram_events_context() as telegram_events_context:
        event = await _collect_event_from_context(
            telegram_events_context,
            build_test_sse_event(),
        )
        assert event.event_type == "message"
        assert event.mode == "private"
        assert event.account == "my_account"
        assert event.update["message"]["id"] == 42


async def test_message_extraction_from_sse_update() -> None:
    """Extract normalized message data from relay updates."""
    from core.telegram_events._runtime_message_handler import extract_message_data

    async with open_telegram_events_context() as telegram_events_context:
        telegram_events_context["fake_relay"].sse_events = [build_test_sse_event()]
        message_data = extract_message_data(
            {
                "message": {
                    "id": 500,
                    "from": {"id": 101, "first_name": "Charlie"},
                    "chat": {"id": 202, "title": "Group Chat"},
                    "text": "Important message",
                    "date": 1704067200,
                }
            },
            "2024-01-01T00:00:00Z",
        )

        assert message_data is not None
        assert (
            message_data["message_id"],
            message_data["sender_name"],
            message_data["chat_name"],
            message_data["text"],
            "timestamp" in message_data,
        ) == (500, "Charlie", "Group Chat", "Important message", True)


async def test_delivery_payload_to_events_engine() -> None:
    """Build delivery payloads that the events-engine expects."""
    from core.telegram_events.service_event_payload import build_message_event_payload

    async with open_telegram_events_context() as telegram_events_context:
        telegram_events_context["fake_relay"].sse_events = [build_test_sse_event()]
        payload = build_message_event_payload(
            {
                "message_id": 777,
                "sender_id": 303,
                "sender_name": "Dave",
                "chat_id": 404,
                "chat_name": "Private",
                "text": "Delivery test",
                "timestamp": "2024-01-01T00:00:00Z",
            },
            target_agent_slug="assistant-alpha",
        )

        assert payload["delivery_id"] == "telegram_404_777"
        assert len(payload["events"]) == 1
        assert payload["events"][0]["event_kind"] == "telegram_message"
        assert payload["events"][0]["to_agent_slug"] == "assistant-alpha"
