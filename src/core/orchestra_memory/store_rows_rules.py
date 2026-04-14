from __future__ import annotations

import uuid
from datetime import UTC, datetime

from core.orchestra_memory.store_validation import (
    normalized_slug,
    required_text,
    validated_limit,
)

MemoryItem = dict[str, str]
ScopedValues = dict[str, str | None]


def build_item(
    *,
    agent_slug: str,
    room: str,
    category: str,
    text: str,
) -> MemoryItem:
    return {
        "memory_id": uuid.uuid4().hex,
        "agent_slug": normalized_slug(agent_slug),
        "room": required_text(room, "room"),
        "category": required_text(category, "category"),
        "text": required_text(text, "text"),
        "created_at": datetime.now(tz=UTC).isoformat(),
    }


def build_scoped_values(
    *,
    agent_slug: str,
    room: str | None,
    category: str | None,
) -> ScopedValues:
    return {
        "wing": normalized_slug(agent_slug),
        "room": room.strip() if room else None,
        "category": category.strip() if category else None,
    }


def normalized_query(query: str) -> str:
    return query.strip().lower()


def validated_search_limit(limit: int) -> int:
    return validated_limit(limit)
