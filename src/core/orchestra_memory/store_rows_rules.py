from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypedDict

from core.orchestra_memory.store_validation import (
    normalized_slug,
    required_text,
    validated_limit,
    validated_optional,
    validated_value,
)

MemoryItem = dict[str, str]


class ScopedValues(TypedDict):
    wing: str
    room: str | None
    category: str | None


@dataclass(frozen=True)
class RuleSets:
    allowed_rooms: set[str]
    allowed_categories: set[str]


def build_item(
    *,
    agent_slug: str,
    room: str,
    category: str,
    text: str,
    rules: RuleSets,
) -> MemoryItem:
    return {
        "memory_id": uuid.uuid4().hex,
        "agent_slug": normalized_slug(agent_slug),
        "room": validated_value(room, rules.allowed_rooms, "room"),
        "category": validated_value(category, rules.allowed_categories, "category"),
        "text": required_text(text, "text"),
        "created_at": datetime.now(tz=UTC).isoformat(),
    }


def build_scoped_values(
    *,
    agent_slug: str,
    room: str | None,
    category: str | None,
    rules: RuleSets,
) -> ScopedValues:
    return {
        "wing": normalized_slug(agent_slug),
        "room": validated_optional(room, rules.allowed_rooms, "room"),
        "category": validated_optional(category, rules.allowed_categories, "category"),
    }


def normalized_query(query: str) -> str:
    return query.strip().lower()


def validated_search_limit(limit: int) -> int:
    return validated_limit(limit)
