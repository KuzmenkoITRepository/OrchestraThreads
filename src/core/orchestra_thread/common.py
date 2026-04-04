"""Shared helpers for the OrchestraThreads MVP."""

from __future__ import annotations

from datetime import datetime, timezone
import unicodedata


THREAD_NON_TERMINAL_STATUSES = {"open", "in_progress", "review"}
THREAD_TERMINAL_STATUSES = {"done", "closed"}
THREAD_NOTIFICATION_STATUSES = {"in_progress", "review", "done", "closed"}
DELIVERED_NOTIFICATION_STATUSES = {"in_progress", "review"}
OWNER_NOTIFICATION_STATUSES = {"in_progress", "done", "closed"}
CALLEE_NOTIFICATION_STATUSES = {"in_progress", "review"}


class ServiceError(RuntimeError):
    """An API-facing service error with an explicit HTTP status."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def normalize_status(value: str) -> str:
    """Normalize a status string for storage and comparisons."""
    return str(value or "").strip().lower()


def normalize_participants(agent_a: str, agent_b: str) -> tuple[str, str]:
    """Normalize a pair of participants so uniqueness is direction-agnostic."""
    left = str(agent_a or "").strip()
    right = str(agent_b or "").strip()
    return (left, right) if left <= right else (right, left)


def normalize_text_input(value: str) -> str:
    """Strip terminal/control garbage and lone surrogates from user-facing text."""
    cleaned: list[str] = []
    for char in str(value or ""):
        codepoint = ord(char)
        if 0xD800 <= codepoint <= 0xDFFF:
            continue
        if char in {"\n", "\r", "\t"}:
            cleaned.append(char)
            continue
        if unicodedata.category(char).startswith("C"):
            continue
        cleaned.append(char)
    return "".join(cleaned)
