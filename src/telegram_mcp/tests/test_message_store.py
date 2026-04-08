"""Tests for the SQLite message metadata store."""

from __future__ import annotations

import unittest

from telegram_mcp.message_store import MessageStore, SendInput


class TestMessageStore(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MessageStore(":memory:")

    def tearDown(self) -> None:
        self.store.close()

    def test_record_and_lookup(self) -> None:
        self.store.record_send(
            SendInput(
                telegram_message_id=100,
                chat_id=999,
                recipient_alias="ivan",
                text="hello",
            )
        )
        record = self.store.lookup(100, 999)
        assert record is not None
        self.assertEqual(record.telegram_message_id, 100)
        self.assertEqual(record.text, "hello")

    def test_lookup_missing(self) -> None:
        self.assertIsNone(self.store.lookup(999, 999))

    def test_update_text(self) -> None:
        self.store.record_send(
            SendInput(
                telegram_message_id=200,
                chat_id=888,
                recipient_alias="ivan",
                text="original",
            )
        )
        self.store.update_text(200, 888, "edited")
        record = self.store.lookup(200, 888)
        assert record is not None
        self.assertEqual(record.text, "edited")

    def test_delete_record(self) -> None:
        self.store.record_send(
            SendInput(
                telegram_message_id=300,
                chat_id=777,
                recipient_alias="ivan",
                text="to delete",
            )
        )
        self.store.delete_record(300, 777)
        self.assertIsNone(self.store.lookup(300, 777))

    def test_record_with_parse_mode_and_reply(self) -> None:
        self.store.record_send(
            SendInput(
                telegram_message_id=400,
                chat_id=999,
                recipient_alias="ivan",
                text="**bold**",
                parse_mode="markdown",
                reply_to_message_id=50,
            )
        )
        record = self.store.lookup(400, 999)
        assert record is not None
        self.assertEqual(record.parse_mode, "markdown")
        self.assertEqual(record.reply_to_message_id, 50)


class TestMessageStoreThreads(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MessageStore(":memory:")

    def tearDown(self) -> None:
        self.store.close()

    def test_list_by_thread_returns_linked_messages(self) -> None:
        self.store.record_send(
            SendInput(
                telegram_message_id=500,
                chat_id=999,
                recipient_alias="ivan",
                text="msg1",
                thread_id="t-abc",
            )
        )
        self.store.record_send(
            SendInput(
                telegram_message_id=501,
                chat_id=999,
                recipient_alias="ivan",
                text="msg2",
                thread_id="t-abc",
            )
        )
        self.store.record_send(
            SendInput(
                telegram_message_id=502,
                chat_id=999,
                recipient_alias="ivan",
                text="other",
                thread_id="t-xyz",
            )
        )
        results = self.store.list_by_thread("t-abc")
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].text, "msg1")
        self.assertEqual(results[1].text, "msg2")

    def test_list_by_thread_empty(self) -> None:
        results = self.store.list_by_thread("nonexistent")
        self.assertEqual(results, [])

    def test_record_with_thread_id(self) -> None:
        self.store.record_send(
            SendInput(
                telegram_message_id=600,
                chat_id=999,
                recipient_alias="ivan",
                text="threaded",
                thread_id="t-123",
            )
        )
        record = self.store.lookup(600, 999)
        assert record is not None
        self.assertEqual(record.thread_id, "t-123")
