"""Tests for the Telegram MCP server: tools, resources, and recipient registry."""

from __future__ import annotations

import unittest
from typing import Any

from telegram_mcp.config import TelegramAuth, TelegramDefaults, TelegramMCPConfig
from telegram_mcp.mcp_server import TelegramMCPServer
from telegram_mcp.recipient_registry import RecipientRegistry
from telegram_mcp.send_request import SendRequest


class _FakeEntity:
    """Minimal Telethon entity stand-in."""

    def __init__(self, chat_id: int) -> None:
        self.id = chat_id
        self.first_name = "Test"
        self.last_name = "User"
        self.username = "testuser"
        self.bot = False


class _FakeDialog:
    """Minimal Telethon dialog stand-in."""

    def __init__(self, entity_id: int, read_outbox_max_id: int) -> None:
        self.entity = _FakeEntity(entity_id)
        self.dialog = type("D", (), {"read_outbox_max_id": read_outbox_max_id})()


class _FakeRawClient:
    """Fake Telethon-level client for edit/delete/info/receipt."""

    def __init__(self) -> None:
        self.edited: list[tuple[Any, int, str]] = []
        self.deleted: list[tuple[Any, int]] = []
        self.read_outbox: int = 0

    async def get_entity(self, chat_id: int) -> _FakeEntity:
        return _FakeEntity(chat_id)

    async def edit_message(self, entity: Any, message_id: int, text: str) -> None:
        self.edited.append((entity, message_id, text))

    async def delete_messages(self, entity: Any, message_ids: list[int]) -> None:
        self.deleted.append((entity, message_ids[0]))

    async def get_dialogs(self, limit: int = 50) -> list[_FakeDialog]:
        return [_FakeDialog(999, self.read_outbox)]


class _FakeClient:
    """Fake TelegramClient that records calls and returns canned results."""

    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []
        self.raw = _FakeRawClient()

    async def close(self) -> None:
        self.sent.clear()

    async def require_client(self) -> _FakeRawClient:
        return self.raw

    async def send_message(self, chat_id: int, text: str) -> dict[str, Any]:
        self.sent.append((chat_id, text))
        return {"ok": True, "message_id": 42, "error": ""}

    async def send_rich(
        self,
        chat_id: int,
        request: SendRequest,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.sent.append((chat_id, request.message))
        return {"ok": True, "message_id": 43, "error": ""}


def _test_config() -> TelegramMCPConfig:
    return TelegramMCPConfig(
        auth=TelegramAuth(api_id=123, api_hash="abc", session_string=None),
        defaults=TelegramDefaults(
            default_recipient="ivan",
            timeout_seconds=10.0,
            max_retries=3,
            log_level="INFO",
        ),
        chat_id_ivan=999,
    )


def _test_registry() -> RecipientRegistry:
    registry = RecipientRegistry(_default_alias="ivan")
    registry.register("ivan", 999)
    registry.register("bob", 888)
    return registry


def _make_server() -> TelegramMCPServer:
    server = TelegramMCPServer(config=_test_config(), registry=_test_registry())
    server.client = _FakeClient()  # type: ignore[assignment]
    server._client_started = True
    return server


class TestToolsList(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.server = _make_server()

    async def asyncTearDown(self) -> None:
        await self.server.close()

    async def test_tools_list_contains_send_tool(self) -> None:
        response = await self.server.handle_request(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
        assert response is not None
        tools = response["result"]["tools"]
        names = {tool["name"] for tool in tools}
        self.assertIn("send_telegram_message", names)
        self.assertIn("edit_telegram_message", names)
        self.assertIn("delete_telegram_message", names)
        self.assertIn("send_telegram_message_batch", names)
        self.assertIn("get_telegram_chat_info", names)
        self.assertIn("check_telegram_read_receipt", names)


class TestSendTool(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.server = _make_server()

    async def asyncTearDown(self) -> None:
        await self.server.close()

    async def test_send_message_default_recipient(self) -> None:
        response = await self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "send_telegram_message",
                    "arguments": {"message": "hello"},
                },
            }
        )
        assert response is not None
        payload = response["result"]["structuredContent"]
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["message_id"], 42)
        self.assertEqual(payload["chat_id"], 999)
        self.assertEqual(payload["recipient"], "ivan")

    async def test_send_message_explicit_recipient(self) -> None:
        response = await self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "send_telegram_message",
                    "arguments": {"message": "hi", "recipient": "ivan"},
                },
            }
        )
        assert response is not None
        payload = response["result"]["structuredContent"]
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["recipient"], "ivan")

    async def test_send_message_unknown_recipient(self) -> None:
        response = await self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "send_telegram_message",
                    "arguments": {"message": "hi", "recipient": "nobody"},
                },
            }
        )
        assert response is not None
        error_payload = response.get("error", {})
        self.assertIn("nobody", str(error_payload.get("message", "")))

    async def test_send_message_empty_text_fails(self) -> None:
        response = await self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "send_telegram_message",
                    "arguments": {"message": "  "},
                },
            }
        )
        assert response is not None
        error = response.get("error")
        self.assertIsNotNone(error)

    async def test_unknown_tool_returns_error(self) -> None:
        result = await self.server.handle_tools_call("nonexistent", {})
        self.assertFalse(result["structuredContent"]["ok"])


class TestResourcesList(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.server = _make_server()

    async def asyncTearDown(self) -> None:
        await self.server.close()

    async def test_resources_list_contains_recipients_and_rate_limits(self) -> None:
        response = await self.server.handle_request(
            {"jsonrpc": "2.0", "id": 10, "method": "resources/list"},
        )
        assert response is not None
        resources = response["result"]["resources"]
        uris = {res["uri"] for res in resources}
        self.assertIn("telegram://recipients", uris)
        self.assertIn("telegram://rate_limits", uris)


class TestResourceRead(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.server = _make_server()

    async def asyncTearDown(self) -> None:
        await self.server.close()

    async def test_read_recipients_resource(self) -> None:
        response = await self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 20,
                "method": "resources/read",
                "params": {"uri": "telegram://recipients"},
            }
        )
        assert response is not None
        payload = response["result"]["structuredContent"]
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["recipients"]["ivan"], 999)

    async def test_read_rate_limits_resource(self) -> None:
        response = await self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 21,
                "method": "resources/read",
                "params": {"uri": "telegram://rate_limits"},
            }
        )
        assert response is not None
        payload = response["result"]["structuredContent"]
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["requests_sent"], 0)
        self.assertIn("window_start", payload)

    async def test_read_unknown_resource(self) -> None:
        response = await self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 22,
                "method": "resources/read",
                "params": {"uri": "telegram://nonexistent"},
            }
        )
        assert response is not None
        payload = response["result"]["structuredContent"]
        self.assertFalse(payload["ok"])


class TestRecipientRegistryUnit(unittest.TestCase):
    def test_resolve_default(self) -> None:
        registry = RecipientRegistry(_default_alias="ivan")
        registry.register("ivan", 999)
        self.assertEqual(registry.resolve(None), 999)

    def test_resolve_explicit(self) -> None:
        registry = RecipientRegistry(_default_alias="ivan")
        registry.register("ivan", 999)
        registry.register("bob", 111)
        self.assertEqual(registry.resolve("bob"), 111)

    def test_resolve_unknown_raises(self) -> None:
        registry = RecipientRegistry(_default_alias="ivan")
        registry.register("ivan", 999)
        with self.assertRaises(ValueError):
            registry.resolve("unknown")

    def test_list_entries(self) -> None:
        registry = RecipientRegistry()
        registry.register("ivan", 999)
        registry.register("bob", 111)
        entries = registry.list_entries()
        self.assertEqual(entries, {"ivan": 999, "bob": 111})

    def test_available_aliases(self) -> None:
        registry = RecipientRegistry()
        registry.register("bob", 111)
        registry.register("alice", 222)
        self.assertEqual(registry.available_aliases(), "alice, bob")


class TestRateLimitTracking(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.server = _make_server()

    async def asyncTearDown(self) -> None:
        await self.server.close()

    async def test_send_increments_request_count(self) -> None:
        await self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 30,
                "method": "tools/call",
                "params": {
                    "name": "send_telegram_message",
                    "arguments": {"message": "test"},
                },
            }
        )
        self.assertEqual(self.server.rate_limits.requests_sent, 1)


class TestSendFormatting(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.server = _make_server()

    async def asyncTearDown(self) -> None:
        await self.server.close()

    async def test_send_with_markdown(self) -> None:
        response = await self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 40,
                "method": "tools/call",
                "params": {
                    "name": "send_telegram_message",
                    "arguments": {"message": "**bold**", "parse_mode": "markdown"},
                },
            }
        )
        assert response is not None
        payload = response["result"]["structuredContent"]
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["message_id"], 43)

    async def test_send_with_html(self) -> None:
        response = await self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 41,
                "method": "tools/call",
                "params": {
                    "name": "send_telegram_message",
                    "arguments": {"message": "<b>bold</b>", "parse_mode": "html"},
                },
            }
        )
        assert response is not None
        payload = response["result"]["structuredContent"]
        self.assertTrue(payload["ok"])

    async def test_send_with_invalid_parse_mode(self) -> None:
        response = await self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 42,
                "method": "tools/call",
                "params": {
                    "name": "send_telegram_message",
                    "arguments": {"message": "hello", "parse_mode": "bbcode"},
                },
            }
        )
        assert response is not None
        error = response.get("error", {})
        self.assertIn("bbcode", str(error.get("message", "")))


class TestSendReply(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.server = _make_server()

    async def asyncTearDown(self) -> None:
        await self.server.close()

    async def test_send_with_reply_to(self) -> None:
        response = await self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 50,
                "method": "tools/call",
                "params": {
                    "name": "send_telegram_message",
                    "arguments": {"message": "reply", "reply_to_message_id": 100},
                },
            }
        )
        assert response is not None
        payload = response["result"]["structuredContent"]
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["message_id"], 43)


class TestSendMedia(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.server = _make_server()

    async def asyncTearDown(self) -> None:
        await self.server.close()

    async def test_send_with_media(self) -> None:
        response = await self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 60,
                "method": "tools/call",
                "params": {
                    "name": "send_telegram_message",
                    "arguments": {
                        "message": "see photo",
                        "media": {"type": "photo", "data": "aGVsbG8="},
                    },
                },
            }
        )
        assert response is not None
        payload = response["result"]["structuredContent"]
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["message_id"], 43)

    async def test_send_with_invalid_media_type(self) -> None:
        response = await self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 61,
                "method": "tools/call",
                "params": {
                    "name": "send_telegram_message",
                    "arguments": {
                        "message": "see file",
                        "media": {"type": "video", "data": "aGVsbG8="},
                    },
                },
            }
        )
        assert response is not None
        error = response.get("error", {})
        self.assertIn("video", str(error.get("message", "")))


class TestEditTool(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.server = _make_server()
        # seed a sent message so the store knows about msg 42
        await self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 70,
                "method": "tools/call",
                "params": {"name": "send_telegram_message", "arguments": {"message": "original"}},
            }
        )

    async def asyncTearDown(self) -> None:
        await self.server.close()

    async def test_edit_message(self) -> None:
        response = await self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 71,
                "method": "tools/call",
                "params": {
                    "name": "edit_telegram_message",
                    "arguments": {"message_id": 42, "new_text": "edited"},
                },
            }
        )
        assert response is not None
        payload = response["result"]["structuredContent"]
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["message_id"], 42)

    async def test_edit_unknown_message(self) -> None:
        response = await self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 72,
                "method": "tools/call",
                "params": {
                    "name": "edit_telegram_message",
                    "arguments": {"message_id": 9999, "new_text": "nope"},
                },
            }
        )
        assert response is not None
        payload = response["result"]["structuredContent"]
        self.assertFalse(payload["ok"])
        self.assertIn("not found", payload["error"])


class TestDeleteTool(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.server = _make_server()
        await self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 80,
                "method": "tools/call",
                "params": {"name": "send_telegram_message", "arguments": {"message": "to delete"}},
            }
        )

    async def asyncTearDown(self) -> None:
        await self.server.close()

    async def test_delete_message(self) -> None:
        response = await self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 81,
                "method": "tools/call",
                "params": {
                    "name": "delete_telegram_message",
                    "arguments": {"message_id": 42},
                },
            }
        )
        assert response is not None
        payload = response["result"]["structuredContent"]
        self.assertTrue(payload["ok"])

    async def test_delete_unknown_message(self) -> None:
        response = await self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 82,
                "method": "tools/call",
                "params": {
                    "name": "delete_telegram_message",
                    "arguments": {"message_id": 9999},
                },
            }
        )
        assert response is not None
        payload = response["result"]["structuredContent"]
        self.assertFalse(payload["ok"])


class TestBatchSend(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.server = _make_server()

    async def asyncTearDown(self) -> None:
        await self.server.close()

    async def test_batch_send_to_two_recipients(self) -> None:
        response = await self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 90,
                "method": "tools/call",
                "params": {
                    "name": "send_telegram_message_batch",
                    "arguments": {"message": "broadcast", "recipients": ["ivan", "bob"]},
                },
            }
        )
        assert response is not None
        payload = response["result"]["structuredContent"]
        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["results"]), 2)
        self.assertTrue(payload["results"][0]["ok"])
        self.assertTrue(payload["results"][1]["ok"])

    async def test_batch_send_empty_recipients_fails(self) -> None:
        response = await self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 91,
                "method": "tools/call",
                "params": {
                    "name": "send_telegram_message_batch",
                    "arguments": {"message": "fail", "recipients": []},
                },
            }
        )
        assert response is not None
        error = response.get("error", {})
        self.assertIn("recipients", str(error.get("message", "")))


class TestThreadResource(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.server = _make_server()

    async def asyncTearDown(self) -> None:
        await self.server.close()

    async def test_thread_resource_returns_linked_messages(self) -> None:
        await self._send_with_thread("msg0", 100)
        await self._send_with_thread("msg1", 101)
        response = await self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 110,
                "method": "resources/read",
                "params": {"uri": "telegram://thread/t-test/messages"},
            }
        )
        assert response is not None
        payload = response["result"]["structuredContent"]
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["thread_id"], "t-test")
        self.assertEqual(len(payload["messages"]), 2)

    async def test_thread_resource_empty(self) -> None:
        response = await self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 120,
                "method": "resources/read",
                "params": {"uri": "telegram://thread/nonexistent/messages"},
            }
        )
        assert response is not None
        payload = response["result"]["structuredContent"]
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["messages"], [])

    async def _send_with_thread(self, text: str, req_id: int) -> None:
        await self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": "tools/call",
                "params": {
                    "name": "send_telegram_message",
                    "arguments": {"message": text, "thread_id": "t-test"},
                },
            }
        )


class TestChatInfoTool(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.server = _make_server()

    async def asyncTearDown(self) -> None:
        await self.server.close()

    async def test_get_chat_info(self) -> None:
        response = await self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 130,
                "method": "tools/call",
                "params": {
                    "name": "get_telegram_chat_info",
                    "arguments": {"recipient": "ivan"},
                },
            }
        )
        assert response is not None
        payload = response["result"]["structuredContent"]
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["chat_id"], 999)
        self.assertEqual(payload["first_name"], "Test")

    async def test_chat_info_cached(self) -> None:
        await self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 131,
                "method": "tools/call",
                "params": {"name": "get_telegram_chat_info", "arguments": {"recipient": "ivan"}},
            }
        )
        cached = self.server.chat_cache.get(999)
        self.assertIsNotNone(cached)


class TestReadReceiptTool(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.server = _make_server()

    async def asyncTearDown(self) -> None:
        await self.server.close()

    async def test_receipt_unread(self) -> None:
        response = await self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 140,
                "method": "tools/call",
                "params": {
                    "name": "check_telegram_read_receipt",
                    "arguments": {"message_id": 42, "recipient": "ivan"},
                },
            }
        )
        assert response is not None
        payload = response["result"]["structuredContent"]
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["probably_read"])
        self.assertIn("disclaimer", payload)

    async def test_receipt_read(self) -> None:
        fake_client = _FakeClient()
        fake_client.raw.read_outbox = 100
        server = TelegramMCPServer(config=_test_config(), registry=_test_registry())
        server.client = fake_client  # type: ignore[assignment]
        server._client_started = True
        response = await server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 141,
                "method": "tools/call",
                "params": {
                    "name": "check_telegram_read_receipt",
                    "arguments": {"message_id": 42, "recipient": "ivan"},
                },
            }
        )
        assert response is not None
        payload = response["result"]["structuredContent"]
        self.assertTrue(payload["probably_read"])
        await server.close()
