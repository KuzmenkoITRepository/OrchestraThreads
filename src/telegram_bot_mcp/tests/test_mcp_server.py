from __future__ import annotations

import asyncio
import unittest

from telegram_bot_mcp.config import TelegramBotMCPConfig
from telegram_bot_mcp.mcp.server import TelegramBotMCPServer

ButtonRows = list[list[dict[str, str]]]


class _FakeClient:
    async def close(self) -> None:
        await asyncio.sleep(0)

    async def send_message(self, *, telegram_user_id: int, text: str) -> dict[str, object]:
        return {"ok": True, "telegram_user_id": telegram_user_id, "text": text}

    async def send_buttons(
        self,
        *,
        telegram_user_id: int,
        text: str,
        buttons: ButtonRows,
    ) -> dict[str, object]:
        return {"ok": True, "telegram_user_id": telegram_user_id, "text": text, "buttons": buttons}

    async def create_survey(
        self,
        *,
        telegram_user_id: int,
        title: str,
        questions: list[dict[str, object]],
    ) -> dict[str, object]:
        return {
            "ok": True,
            "telegram_user_id": telegram_user_id,
            "title": title,
            "questions": questions,
        }

    async def get_history(
        self,
        *,
        telegram_user_id: int,
        limit: int,
        session_id: str | None,
    ) -> dict[str, object]:
        return {
            "ok": True,
            "telegram_user_id": telegram_user_id,
            "limit": limit,
            "session_id": session_id,
        }


class TelegramBotMCPServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.server = TelegramBotMCPServer(
            config=TelegramBotMCPConfig(
                listener_url="http://127.0.0.1:8791",
                listener_api_token="listener-test-token",
                timeout_seconds=10.0,
                log_level="INFO",
            )
        )
        self.server.client = _FakeClient()  # type: ignore[assignment]

    async def asyncTearDown(self) -> None:
        await self.server.close()

    async def test_tools_list_contains_bot_tools(self) -> None:
        response = await self.server.handle_request(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        )
        assert response is not None
        tools = response["result"]["tools"]
        self.assertEqual(len(tools), 4)
        self.assertEqual(tools[0]["name"], "send_telegram_bot_message")

    async def test_send_message_tool(self) -> None:
        response = await self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "send_telegram_bot_message",
                    "arguments": {"telegram_user_id": 42, "text": "hello"},
                },
            }
        )
        assert response is not None
        payload = response["result"]["structuredContent"]
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["telegram_user_id"], 42)

    async def test_get_history_tool(self) -> None:
        response = await self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "get_telegram_bot_history",
                    "arguments": {"telegram_user_id": 42, "session_id": "abc", "limit": 5},
                },
            }
        )
        assert response is not None
        payload = response["result"]["structuredContent"]
        self.assertEqual(payload["session_id"], "abc")
        self.assertEqual(payload["limit"], 5)
