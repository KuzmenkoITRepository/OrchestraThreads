"""SQLite-backed metadata store for sent Telegram messages."""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

_STORE_PATH_ENV = "TELEGRAM_STORE_PATH"
_DEFAULT_STORE_FILE = "telegram_mcp_messages.db"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS sent_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_message_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    recipient_alias TEXT NOT NULL,
    text TEXT NOT NULL,
    parse_mode TEXT,
    reply_to_message_id INTEGER,
    thread_id TEXT,
    sent_at TEXT NOT NULL
)
"""

_INSERT = """
INSERT INTO sent_messages
    (telegram_message_id, chat_id, recipient_alias, text, parse_mode, reply_to_message_id, thread_id, sent_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""

_SELECT_BY_MSG_ID = """
SELECT id, telegram_message_id, chat_id, recipient_alias, text,
    parse_mode, reply_to_message_id, thread_id, sent_at
FROM sent_messages WHERE telegram_message_id = ? AND chat_id = ?
ORDER BY sent_at DESC LIMIT 1
"""

_SELECT_BY_THREAD = """
SELECT id, telegram_message_id, chat_id, recipient_alias, text,
    parse_mode, reply_to_message_id, thread_id, sent_at
FROM sent_messages WHERE thread_id = ?
ORDER BY sent_at ASC
"""

_UPDATE_TEXT = """
UPDATE sent_messages SET text = ? WHERE telegram_message_id = ? AND chat_id = ?
"""

_DELETE_ROW = """
DELETE FROM sent_messages WHERE telegram_message_id = ? AND chat_id = ?
"""


@dataclass(frozen=True)
class SentRecord:
    """One row from the sent_messages table."""

    row_id: int
    telegram_message_id: int
    chat_id: int
    recipient_alias: str
    text: str
    parse_mode: str | None
    reply_to_message_id: int | None
    thread_id: str | None
    sent_at: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict (excluding row_id)."""
        return {
            "telegram_message_id": self.telegram_message_id,
            "chat_id": self.chat_id,
            "recipient_alias": self.recipient_alias,
            "text": self.text,
            "parse_mode": self.parse_mode,
            "reply_to_message_id": self.reply_to_message_id,
            "thread_id": self.thread_id,
            "sent_at": self.sent_at,
        }


class MessageStore:
    """Thin SQLite wrapper for sent message metadata."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(_CREATE_TABLE)
        self._conn.commit()

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()

    def record_send(self, record: SendInput) -> None:
        """Insert a sent message record."""
        final = record.with_timestamp()
        self._conn.execute(
            _INSERT,
            (
                final.telegram_message_id,
                final.chat_id,
                final.recipient_alias,
                final.text,
                final.parse_mode,
                final.reply_to_message_id,
                final.thread_id,
                final.sent_at,
            ),
        )
        self._conn.commit()

    def lookup(self, telegram_message_id: int, chat_id: int) -> SentRecord | None:
        """Find a sent record by Telegram message ID and chat ID."""
        row = self._conn.execute(
            _SELECT_BY_MSG_ID,
            (telegram_message_id, chat_id),
        ).fetchone()
        if row is None:
            return None
        return _row_to_record(row)

    def update_text(self, telegram_message_id: int, chat_id: int, new_text: str) -> None:
        """Update the stored text after a successful edit."""
        self._conn.execute(_UPDATE_TEXT, (new_text, telegram_message_id, chat_id))
        self._conn.commit()

    def delete_record(self, telegram_message_id: int, chat_id: int) -> None:
        """Remove a record after a successful delete."""
        self._conn.execute(_DELETE_ROW, (telegram_message_id, chat_id))
        self._conn.commit()

    def list_by_thread(self, thread_id: str) -> list[SentRecord]:
        """Return all sent records for a given thread_id."""
        rows = self._conn.execute(_SELECT_BY_THREAD, (thread_id,)).fetchall()
        return [_row_to_record(row) for row in rows]


@dataclass(frozen=True)
class SendInput:
    """Parameters for record_send — avoids long argument lists."""

    telegram_message_id: int
    chat_id: int
    recipient_alias: str
    text: str
    parse_mode: str | None = None
    reply_to_message_id: int | None = None
    thread_id: str | None = None
    sent_at: str = ""

    def with_timestamp(self) -> SendInput:
        """Return a copy with sent_at set to current UTC time."""
        if self.sent_at:
            return self
        return SendInput(
            telegram_message_id=self.telegram_message_id,
            chat_id=self.chat_id,
            recipient_alias=self.recipient_alias,
            text=self.text,
            parse_mode=self.parse_mode,
            reply_to_message_id=self.reply_to_message_id,
            thread_id=self.thread_id,
            sent_at=datetime.now(tz=UTC).isoformat(),
        )


def _row_to_record(row: tuple[Any, ...]) -> SentRecord:
    return SentRecord(
        row_id=row[0],
        telegram_message_id=row[1],
        chat_id=row[2],
        recipient_alias=row[3],
        text=row[4],
        parse_mode=row[5],
        reply_to_message_id=row[6],
        thread_id=row[7],
        sent_at=row[8],
    )


def default_db_path() -> str:
    """Return the store path from env or a sensible file default."""
    return os.getenv(_STORE_PATH_ENV, "").strip() or _DEFAULT_STORE_FILE
