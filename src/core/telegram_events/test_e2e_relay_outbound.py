"""Outbound pytest E2E coverage for Telegram relay integration."""

from __future__ import annotations

import asyncio
from typing import Any

from aiohttp import ClientSession

from core.telegram_events.conftest import open_telegram_events_context


async def post_send(
    telegram_events_server: Any,
    headers: dict[str, str] | None,
    payload: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """POST to the telegram-events send endpoint."""
    async with ClientSession() as session:
        async with session.post(
            telegram_events_server.make_url("/send"),
            headers=headers,
            json=payload,
        ) as response:
            return response.status, await response.json()


async def test_send_rejects_invalid_authorization() -> None:
    """Reject outbound send calls without a valid relay token."""
    async with open_telegram_events_context() as telegram_events_context:
        telegram_events_server = telegram_events_context["telegram_events_server"]
        payload = {"chat_id": 123, "message": "hello"}
        responses = await asyncio.gather(
            post_send(telegram_events_server, headers=None, payload=payload),
            post_send(
                telegram_events_server,
                headers={"Authorization": "Bearer wrong-token"},
                payload=payload,
            ),
            post_send(
                telegram_events_server,
                headers={"Authorization": "wrong-token"},
                payload=payload,
            ),
            post_send(
                telegram_events_server,
                headers={"Authorization": "Bearer "},
                payload=payload,
            ),
        )
        assert [status for status, _ in responses] == [401, 401, 401, 401]


async def test_send_json_rpc_forwarding() -> None:
    """Forward `/send` requests to the relay as MCP JSON-RPC."""
    async with open_telegram_events_context() as telegram_events_context:
        fake_relay = telegram_events_context["fake_relay"]
        bearer_token = telegram_events_context["bearer_token"]

        status, _ = await post_send(
            telegram_events_context["telegram_events_server"],
            headers={"Authorization": f"Bearer {bearer_token}"},
            payload={"chat_id": 999, "message": "test message"},
        )

        assert status == 200
        assert len(fake_relay.mcp_calls) == 1
        mcp_call = fake_relay.mcp_calls[0]
        assert mcp_call["jsonrpc"] == "2.0"
        assert mcp_call["method"] == "tools/call"
        assert mcp_call["params"] == {
            "name": "send_telegram_message",
            "arguments": {"chat_id": "999", "message": "test message"},
        }


async def test_send_extracts_message_id_structured() -> None:
    """Read structured relay responses with nested message IDs."""
    async with open_telegram_events_context() as telegram_events_context:
        fake_relay = telegram_events_context["fake_relay"]
        bearer_token = telegram_events_context["bearer_token"]
        fake_relay.mcp_response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"content": [{"text": {"structuredContent": {"messageId": 67890}}}]},
        }

        status, result = await post_send(
            telegram_events_context["telegram_events_server"],
            headers={"Authorization": f"Bearer {bearer_token}"},
            payload={"chat_id": 123, "message": "hello"},
        )

        assert status == 200
        assert result["message_id"] == 67890


async def test_send_extracts_message_id_legacy_dict() -> None:
    """Read legacy relay responses that return `message_id` dictionaries."""
    async with open_telegram_events_context() as telegram_events_context:
        fake_relay = telegram_events_context["fake_relay"]
        bearer_token = telegram_events_context["bearer_token"]
        fake_relay.mcp_response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"content": [{"text": {"message_id": 11111}}]},
        }

        status, result = await post_send(
            telegram_events_context["telegram_events_server"],
            headers={"Authorization": f"Bearer {bearer_token}"},
            payload={"chat_id": 123, "message": "hello"},
        )

        assert status == 200
        assert result["message_id"] == 11111


async def test_send_extracts_message_id_numeric_string() -> None:
    """Read numeric-string relay responses as message IDs."""
    async with open_telegram_events_context() as telegram_events_context:
        fake_relay = telegram_events_context["fake_relay"]
        bearer_token = telegram_events_context["bearer_token"]
        fake_relay.mcp_response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"content": [{"text": "22222"}]},
        }

        status, result = await post_send(
            telegram_events_context["telegram_events_server"],
            headers={"Authorization": f"Bearer {bearer_token}"},
            payload={"chat_id": 123, "message": "hello"},
        )

        assert status == 200
        assert result["message_id"] == 22222


async def test_send_relay_service_unavailable() -> None:
    """Surface relay outages as send failures."""
    async with open_telegram_events_context() as telegram_events_context:
        fake_relay = telegram_events_context["fake_relay"]
        bearer_token = telegram_events_context["bearer_token"]
        fake_relay.mcp_status = 503

        status, result = await post_send(
            telegram_events_context["telegram_events_server"],
            headers={"Authorization": f"Bearer {bearer_token}"},
            payload={"chat_id": 123, "message": "hello"},
        )

        assert status == 502
        assert "Relay returned 503" in result["error"]
