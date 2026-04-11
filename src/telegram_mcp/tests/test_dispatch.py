from __future__ import annotations

import unittest
from typing import Any

from telegram_mcp.config import TelegramDefaults, TelegramMCPConfig
from telegram_mcp.mcp.dispatch import dispatch_request
from telegram_mcp.mcp.payloads import SEND_TELEGRAM_MESSAGE_TOOL
from telegram_mcp.mcp.server import TelegramMCPServer, telegram_tool_definitions


class TelegramMCPDispatchTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        config = TelegramMCPConfig(
            telegram_events_url="http://localhost:9999",
            defaults=TelegramDefaults(default_recipient="ivan", log_level="INFO"),
            chat_id_ivan=12345,
        )
        self.server = TelegramMCPServer(config=config)

    async def test_dispatch_unknown_tool_returns_mcp_error(self) -> None:
        response = await dispatch_request(
            self.server,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "unknown", "arguments": {}},
            },
        )
        assert response is not None
        self.assertFalse(response["result"]["structuredContent"]["ok"])

    async def test_dispatch_missing_msg_error(self) -> None:
        response = await dispatch_request(
            self.server,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": SEND_TELEGRAM_MESSAGE_TOOL, "arguments": {}},
            },
        )
        assert response is not None
        structured = response["result"]["structuredContent"]
        self.assertFalse(structured["ok"])
        self.assertIn("required", structured["error"])

    async def test_dispatch_non_dict_error(self) -> None:
        bad_request: Any = [1, 2, 3]
        response = await dispatch_request(self.server, bad_request)
        assert response is not None
        self.assertEqual(response["error"]["code"], -32600)

    async def test_handle_tools_call_unknown_tool(self) -> None:
        response = await self.server.handle_tools_call(name="unknown", arguments={})
        self.assertFalse(response["structuredContent"]["ok"])

    async def test_handle_tools_call_missing_message(self) -> None:
        response = await self.server.handle_tools_call(
            name=SEND_TELEGRAM_MESSAGE_TOOL,
            arguments={},
        )
        self.assertFalse(response["structuredContent"]["ok"])

    def test_telegram_tool_definitions_returns_list(self) -> None:
        tools = telegram_tool_definitions()
        self.assertIsInstance(tools, list)
        self.assertTrue(any(item["name"] == SEND_TELEGRAM_MESSAGE_TOOL for item in tools))
