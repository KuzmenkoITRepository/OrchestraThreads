"""Typed chat metadata with TTL cache, backed by Telethon get_entity."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

_CACHE_TTL = timedelta(minutes=5)


@dataclass(frozen=True)
class ChatInfo:
    """Snapshot of Telegram chat/user metadata."""

    chat_id: int
    chat_type: str
    title: str
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    is_bot: bool = False
    fetched_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict."""
        return {
            "chat_id": self.chat_id,
            "chat_type": self.chat_type,
            "title": self.title,
            "username": self.username,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "is_bot": self.is_bot,
            "fetched_at": self.fetched_at,
        }


class ChatInfoCache:
    """In-memory TTL cache for ChatInfo lookups."""

    def __init__(self) -> None:
        self._store: dict[int, tuple[ChatInfo, datetime]] = {}

    def get(self, chat_id: int) -> ChatInfo | None:
        """Return cached ChatInfo if fresh, else None."""
        entry = self._store.get(chat_id)
        if entry is None:
            return None
        info, cached_at = entry
        if datetime.now(tz=UTC) - cached_at > _CACHE_TTL:
            self._store.pop(chat_id, None)
            return None
        return info

    def put(self, info: ChatInfo) -> None:
        """Store a ChatInfo entry with current timestamp."""
        self._store[info.chat_id] = (info, datetime.now(tz=UTC))


async def fetch_chat_info(client: Any, chat_id: int) -> ChatInfo:
    """Fetch chat metadata from Telethon and return typed ChatInfo."""
    entity = await client.get_entity(chat_id)
    return _entity_to_chat_info(entity, chat_id)


def _entity_to_chat_info(entity: Any, chat_id: int) -> ChatInfo:
    type_name = type(entity).__name__.lower()
    chat_type = _classify_type(type_name)
    title = str(getattr(entity, "title", "") or "")
    first = str(getattr(entity, "first_name", "") or "")
    if not title:
        title = first or str(chat_id)
    return ChatInfo(
        chat_id=chat_id,
        chat_type=chat_type,
        title=title,
        username=str(getattr(entity, "username", "") or "") or None,
        first_name=first or None,
        last_name=str(getattr(entity, "last_name", "") or "") or None,
        is_bot=bool(getattr(entity, "bot", False)),
        fetched_at=datetime.now(tz=UTC).isoformat(),
    )


def _classify_type(type_name: str) -> str:
    if "user" in type_name:
        return "user"
    if "channel" in type_name:
        return "channel"
    if "chat" in type_name:
        return "group"
    return "unknown"
