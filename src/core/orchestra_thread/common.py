"""Shared helpers for the OrchestraThreads MVP."""

from __future__ import annotations

import unicodedata
from datetime import UTC, datetime
from typing import Final

THREAD_NON_TERMINAL_STATUSES: Final = frozenset(("open", "in_progress", "review"))
THREAD_TERMINAL_STATUSES: Final = frozenset(("done", "closed"))
THREAD_NOTIFICATION_STATUSES: Final = frozenset(("in_progress", "review", "done", "closed"))
DELIVERED_NOTIFICATION_STATUSES: Final = frozenset(("in_progress", "review"))
OWNER_NOTIFICATION_STATUSES: Final = frozenset(("in_progress", "done", "closed"))
CALLEE_NOTIFICATION_STATUSES: Final = frozenset(("in_progress", "review"))


class ServiceError(RuntimeError):
    """An API-facing service error with an explicit HTTP status."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(UTC).isoformat()


def normalize_status(value: str) -> str:
    """Normalize a status string for storage and comparisons."""
    return str(value or "").strip().lower()


def normalize_participants(agent_a: str, agent_b: str) -> tuple[str, str]:
    """Normalize a pair of participants so uniqueness is direction-agnostic."""
    left = str(agent_a or "").strip()
    right = str(agent_b or "").strip()
    return (left, right) if left <= right else (right, left)


_PASSTHROUGH_WHITESPACE = frozenset(("\n", "\r", "\t"))


def _is_printable_char(char: str) -> bool:
    """Return True if the character should be kept in cleaned text."""
    codepoint = ord(char)
    if 0xD800 <= codepoint <= 0xDFFF:
        return False
    if char in _PASSTHROUGH_WHITESPACE:
        return True
    return not unicodedata.category(char).startswith("C")


def normalize_text_input(value: str) -> str:
    """Strip terminal/control garbage and lone surrogates from user-facing text."""
    normalized = str(value or "")
    chars = [char for char in normalized if _is_printable_char(char)]
    return "".join(chars)
