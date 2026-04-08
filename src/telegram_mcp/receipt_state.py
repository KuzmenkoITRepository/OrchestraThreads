"""Best-effort read receipt hints — explicitly non-authoritative.

Telegram's MTProto exposes ``readOutboxMaxId`` on dialogs:
if a sent message_id <= readOutboxMaxId, the peer has opened the chat
up to that point.  This works reliably only for private chats and is
a *hint*, not a guarantee — Telegram does not promise real-time or
complete read-receipt semantics.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

_DISCLAIMER = (
    "Best-effort hint only. Telegram does not guarantee read-receipt accuracy, "
    "especially in group chats."
)


@dataclass(frozen=True)
class ReadReceiptHint:
    """Non-authoritative delivery/read hint for a sent message."""

    message_id: int
    chat_id: int
    probably_read: bool
    checked_at: str
    disclaimer: str = _DISCLAIMER

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict."""
        return {
            "message_id": self.message_id,
            "chat_id": self.chat_id,
            "probably_read": self.probably_read,
            "checked_at": self.checked_at,
            "disclaimer": self.disclaimer,
        }


async def check_read_receipt(
    client: Any,
    chat_id: int,
    message_id: int,
) -> ReadReceiptHint:
    """Best-effort check whether a message was likely read.

    Uses Telethon's get_dialogs to find the read-outbox high-water mark.
    Falls back to ``probably_read=False`` on any error.
    """
    probably_read = await _probe_read_status(client, chat_id, message_id)
    return ReadReceiptHint(
        message_id=message_id,
        chat_id=chat_id,
        probably_read=probably_read,
        checked_at=datetime.now(tz=UTC).isoformat(),
    )


async def _probe_read_status(
    client: Any,
    chat_id: int,
    message_id: int,
) -> bool:
    try:
        dialogs = await client.get_dialogs(limit=50)
    except Exception:
        logger.debug("get_dialogs failed; assuming unread", exc_info=True)
        return False
    return _find_read_mark(dialogs, chat_id, message_id)


def _find_read_mark(
    dialogs: Any,
    chat_id: int,
    message_id: int,
) -> bool:
    for dialog in dialogs:
        entity = getattr(dialog, "entity", None)
        entity_id = int(getattr(entity, "id", 0) or 0)
        if entity_id != chat_id:
            continue
        raw = getattr(dialog, "dialog", None)
        outbox_max = int(getattr(raw, "read_outbox_max_id", 0) or 0)
        return message_id <= outbox_max
    return False
