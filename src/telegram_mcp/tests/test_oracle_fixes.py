"""Targeted tests for Oracle-identified gaps: recipient mutation, store durability,
batch partial failure, file-path media, chat resource fetch, config knobs."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from telegram_mcp.config import TelegramAuth, TelegramDefaults, TelegramMCPConfig
from telegram_mcp.mcp_server import TelegramMCPServer
from telegram_mcp.message_store import MessageStore, SendInput, default_db_path
from telegram_mcp.recipient_registry import RecipientRegistry
from telegram_mcp.send_request import SendRequest, validate_media


class _FakeEntity:
    def __init__(self, cid: int) -> None:
        self.id = cid
        self.first_name = "Test"
        self.last_name = "U"
        self.username = "test"
        self.bot = False


class _FakeRawClient:
    def __init__(self) -> None:
        self.edited: list[tuple[Any, int, str]] = []
        self.read_outbox: int = 0

    async def get_entity(self, chat_id: int) -> _FakeEntity:
        return _FakeEntity(chat_id)

    async def edit_message(self, entity: Any, mid: int, text: str) -> None:
        self.edited.append((entity, mid, text))

    async def delete_messages(self, entity: Any, ids: list[int]) -> None:
        self.edited.append((entity, ids[0], ""))

    async def get_dialogs(self, limit: int = 50) -> list[Any]:
        return []


class _FakeClient:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []
        self.raw = _FakeRawClient()

    async def close(self) -> None:
        self.sent.clear()

    async def require_client(self) -> _FakeRawClient:
        return self.raw

    async def send_message(self, cid: int, text: str) -> dict[str, Any]:
        self.sent.append((cid, text))
        return {"ok": True, "message_id": 42, "error": ""}

    async def send_rich(
        self,
        cid: int,
        request: SendRequest,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.sent.append((cid, request.message))
        return {"ok": True, "message_id": 43, "error": ""}


def _cfg() -> TelegramMCPConfig:
    return TelegramMCPConfig(
        auth=TelegramAuth(api_id=1, api_hash="x", session_string=None),
        defaults=TelegramDefaults(
            default_recipient="ivan",
            timeout_seconds=5.0,
            max_retries=2,
            log_level="INFO",
        ),
        chat_id_ivan=999,
    )


def _server() -> TelegramMCPServer:
    reg = RecipientRegistry(_default_alias="ivan")
    reg.register("ivan", 999)
    reg.register("bob", 888)
    srv = TelegramMCPServer(
        config=_cfg(),
        registry=reg,
        store=MessageStore(":memory:"),
    )
    srv.client = _FakeClient()  # type: ignore[assignment]
    srv._client_started = True
    return srv


class TestRecipientMutation(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.server = _server()

    async def asyncTearDown(self) -> None:
        await self.server.close()

    async def test_upsert_adds_recipient(self) -> None:
        resp = await self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "upsert_recipient",
                    "arguments": {"alias": "carol", "chat_id": 777},
                },
            }
        )
        assert resp is not None
        payload = resp["result"]["structuredContent"]
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["recipients"]["carol"], 777)

    async def test_remove_recipient(self) -> None:
        resp = await self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "remove_recipient", "arguments": {"alias": "bob"}},
            }
        )
        assert resp is not None
        self.assertTrue(resp["result"]["structuredContent"]["removed"])


class TestRegistryFilePersistence(unittest.TestCase):
    def test_register_persists_to_file(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            path = Path(tmp.name)
        registry = RecipientRegistry(_persist_path=path)
        registry.register("dave", 555)
        raw = json.loads(path.read_text())
        self.assertEqual(raw["dave"], 555)
        path.unlink()


class TestStoreDurability(unittest.TestCase):
    def test_default_db_path_not_memory(self) -> None:
        path = default_db_path()
        self.assertNotEqual(path, ":memory:")
        self.assertTrue(path.endswith(".db"))

    def test_file_backed_survives_reopen(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name
        store_a = MessageStore(db_path)
        store_a.record_send(
            SendInput(
                telegram_message_id=999,
                chat_id=111,
                recipient_alias="ivan",
                text="durable",
            )
        )
        store_a.close()
        store_b = MessageStore(db_path)
        record = store_b.lookup(999, 111)
        store_b.close()
        Path(db_path).unlink()
        assert record is not None
        self.assertEqual(record.text, "durable")


class TestBatchPartialFailure(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.server = _server()

    async def asyncTearDown(self) -> None:
        await self.server.close()

    async def test_mixed_success_and_failure(self) -> None:
        resp = await self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 10,
                "method": "tools/call",
                "params": {
                    "name": "send_telegram_message_batch",
                    "arguments": {"message": "hi", "recipients": ["ivan", "nonexistent"]},
                },
            }
        )
        assert resp is not None
        payload = resp["result"]["structuredContent"]
        self.assertTrue(payload["ok"])
        results = payload["results"]
        self.assertEqual(len(results), 2)
        self.assertTrue(results[0]["ok"])
        self.assertFalse(results[1]["ok"])
        self.assertIn("nonexistent", results[1]["error"])


class TestFilePathMedia(unittest.TestCase):
    def test_validate_media_with_path(self) -> None:
        media = validate_media({"type": "document", "path": "/tmp/report.pdf"})
        self.assertEqual(media.source, "file")
        self.assertEqual(media.data, "/tmp/report.pdf")
        self.assertEqual(media.filename, "report.pdf")

    def test_validate_media_base64_still_works(self) -> None:
        media = validate_media({"type": "photo", "data": "aGVsbG8="})
        self.assertEqual(media.source, "base64")


class TestChatResourceFetch(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.server = _server()

    async def asyncTearDown(self) -> None:
        await self.server.close()

    async def test_cache_miss_fetches_from_client(self) -> None:
        resp = await self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 20,
                "method": "resources/read",
                "params": {"uri": "telegram://chat/ivan/info"},
            }
        )
        assert resp is not None
        payload = resp["result"]["structuredContent"]
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["chat_id"], 999)
        self.assertIn("fetched_at", payload)


class TestConfigKnobs(unittest.TestCase):
    def test_max_retries_flows_to_client(self) -> None:
        from telegram_mcp.telegram_client import TelegramClient as TC

        client = TC(api_id=1, api_hash="x", max_retries=7, timeout_seconds=42.0)
        self.assertEqual(client._max_retries, 7)
        self.assertEqual(client._timeout, 42.0)
