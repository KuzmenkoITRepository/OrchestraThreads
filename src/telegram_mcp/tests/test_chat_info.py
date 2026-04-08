"""Tests for chat_info cache and entity parsing."""

from __future__ import annotations

import unittest

from telegram_mcp.chat_info import ChatInfoCache, _entity_to_chat_info


class _FakeUser:
    id: int = 123
    first_name: str = "Alice"
    last_name: str = "Smith"
    username: str = "alice"
    bot: bool = False


class _FakeChannel:
    id: int = 456
    title: str = "News"
    username: str = "news_ch"


class TestEntityToChatInfo(unittest.TestCase):
    def test_user_entity(self) -> None:
        info = _entity_to_chat_info(_FakeUser(), 123)
        self.assertEqual(info.chat_type, "user")
        self.assertEqual(info.title, "Alice")
        self.assertEqual(info.username, "alice")

    def test_channel_entity(self) -> None:
        info = _entity_to_chat_info(_FakeChannel(), 456)
        self.assertEqual(info.chat_type, "channel")
        self.assertEqual(info.title, "News")


class TestChatInfoCache(unittest.TestCase):
    def test_put_and_get(self) -> None:
        cache = ChatInfoCache()
        info = _entity_to_chat_info(_FakeUser(), 123)
        cache.put(info)
        self.assertIsNotNone(cache.get(123))

    def test_get_missing(self) -> None:
        cache = ChatInfoCache()
        self.assertIsNone(cache.get(999))
