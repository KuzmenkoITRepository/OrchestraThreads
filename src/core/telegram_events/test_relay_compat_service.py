from __future__ import annotations

import json
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

from core.telegram_events.relay_compat_config import RelayCompatConfig
from core.telegram_events.relay_compat_service import TelegramRelayCompatService


@dataclass
class _FakeListener:
    client: object | None = object()

    async def start_client(self) -> object:
        if self.client is None:
            self.client = object()
        return self.client

    async def stop(self) -> None:
        self.client = None


def _config() -> RelayCompatConfig:
    return RelayCompatConfig(
        host="127.0.0.1",
        port=3000,
        bearer_token="secret-token",
        api_id=1,
        api_hash="hash",
        session_string="session",
        session_file=None,
        recipient_chat_ids={"ivan": "748976004"},
    )


async def test_handle_json_rpc_accepts_chat_id() -> None:
    service = TelegramRelayCompatService(_config(), listener=_FakeListener())
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "send_telegram_message",
            "arguments": {"chat_id": "999", "message": "hello"},
        },
    }

    with patch(
        "core.telegram_events.relay_compat_rpc.send_text_message",
        new=AsyncMock(return_value=321),
    ) as send_mock:
        result = await service.handle_json_rpc(payload)
        send_mock.assert_awaited_once_with(service._listener.client, "999", "hello")

    assert _message_id(result) == 321


async def test_handle_json_rpc_accepts_recipient() -> None:
    service = TelegramRelayCompatService(_config(), listener=_FakeListener())
    payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "send_telegram_message",
            "arguments": {"recipient": "ivan", "message": "hello"},
        },
    }

    with patch(
        "core.telegram_events.relay_compat_rpc.send_text_message",
        new=AsyncMock(return_value=654),
    ) as send_mock:
        result = await service.handle_json_rpc(payload)
        send_mock.assert_awaited_once_with(service._listener.client, "748976004", "hello")

    assert _message_id(result) == 654


async def test_handle_json_rpc_rejects_recipient() -> None:
    service = TelegramRelayCompatService(_config(), listener=_FakeListener())
    payload = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "send_telegram_message",
            "arguments": {"recipient": "unknown", "message": "hello"},
        },
    }

    result = await service.handle_json_rpc(payload)

    assert result["error"]["message"] == "Unknown recipient: unknown"


async def test_handle_message_broadcasts_sse_payload() -> None:
    service = TelegramRelayCompatService(_config(), listener=_FakeListener())
    subscriber = service.subscribe()

    await service._handle_message(
        {
            "chat_id": "321",
            "chat_name": "Chat",
            "message_id": 42,
            "sender_name": "Bob",
            "user_id": "7",
            "text": "Hello",
            "timestamp": "2024-01-01T12:00:00Z",
        }
    )
    payload = await subscriber.get()
    assert payload is not None
    event = json.loads(payload)

    assert event["event_type"] == "message"
    assert event["update"]["message"]["chat"]["id"] == 321
    assert event["update"]["message"]["text"] == "Hello"


def _message_id(result: dict[str, object]) -> int:
    structured = result["result"]
    assert isinstance(structured, dict)
    content = structured["content"]
    assert isinstance(content, list)
    payload = content[0]["text"]
    assert isinstance(payload, dict)
    message = payload["structuredContent"]
    assert isinstance(message, dict)
    return int(message["messageId"])
