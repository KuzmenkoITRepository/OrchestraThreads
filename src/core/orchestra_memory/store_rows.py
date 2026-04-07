from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

from core.orchestra_memory.store_validation import (
    normalized_slug,
    required_text,
    validated_limit,
    validated_optional,
    validated_value,
)

MemoryItem = dict[str, str]
StorePayload = dict[str, object]


@dataclass(frozen=True)
class MemoryRow:
    memory_id: str
    wing: str
    room: str
    category: str
    text: str
    created_at: str

    def as_item(self) -> MemoryItem:
        return {
            "memory_id": self.memory_id,
            "agent_slug": self.wing,
            "room": self.room,
            "category": self.category,
            "text": self.text,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class ScopedFilters:
    wing: str
    room: str | None
    category: str | None

    def to_where(self) -> dict[str, object]:
        clauses: list[dict[str, str]] = [{"wing": self.wing}]
        if self.room is not None:
            clauses.append({"room": self.room})
        if self.category is not None:
            clauses.append({"category": self.category})
        if len(clauses) == 1:
            return {"wing": self.wing}
        return {"$and": clauses}


@dataclass(frozen=True)
class SearchRequest:
    filters: ScopedFilters
    query: str
    limit: int

    def matches(self, payload: StorePayload) -> list[MemoryItem]:
        items = list(reversed(self._payload_items(payload)))
        matched = [item for item in items if self._matches_query(item)]
        return matched[: self.limit]

    def _payload_items(self, payload: StorePayload) -> list[MemoryItem]:
        result: list[MemoryItem] = []
        for memory_id, text, metadata in self._payload_rows(payload):
            item = self._item_from_row(memory_id=memory_id, text=text, metadata=metadata)
            if item is not None:
                result.append(item)
        return result

    def _payload_rows(self, payload: StorePayload) -> Iterator[tuple[object, object, object]]:
        return zip(
            self._payload_list(payload, "ids"),
            self._payload_list(payload, "documents"),
            self._payload_list(payload, "metadatas"),
            strict=True,
        )

    def _payload_list(self, payload: StorePayload, key: str) -> list[object]:
        value = payload.get(key, [])
        return value if isinstance(value, list) else []

    def _item_from_row(
        self,
        *,
        memory_id: object,
        text: object,
        metadata: object,
    ) -> MemoryItem | None:
        row = _memory_row(memory_id=memory_id, text=text, metadata=metadata)
        if row is None:
            return None
        return row.as_item()

    def _matches_query(self, item: MemoryItem) -> bool:
        if not self.query:
            return True
        return self.query in item["text"].lower()


@dataclass(frozen=True)
class StoreRules:
    allowed_rooms: set[str]
    allowed_categories: set[str]

    def build_item(self, *, agent_slug: str, room: str, category: str, text: str) -> MemoryItem:
        return {
            "memory_id": uuid.uuid4().hex,
            "agent_slug": normalized_slug(agent_slug),
            "room": validated_value(room, self.allowed_rooms, "room"),
            "category": validated_value(category, self.allowed_categories, "category"),
            "text": required_text(text, "text"),
            "created_at": datetime.now(tz=UTC).isoformat(),
        }

    @staticmethod
    def metadata_from_item(item: MemoryItem) -> dict[str, object]:
        return {
            "wing": item["agent_slug"],
            "room": item["room"],
            "category": item["category"],
            "created_at": item["created_at"],
        }

    def build_search_request(
        self,
        *,
        agent_slug: str,
        query: str,
        room: str | None,
        category: str | None,
        limit: int,
    ) -> SearchRequest:
        return SearchRequest(
            filters=self.scoped_filters(agent_slug=agent_slug, room=room, category=category),
            query=query.strip().lower(),
            limit=validated_limit(limit),
        )

    def scoped_filters(
        self,
        *,
        agent_slug: str,
        room: str | None,
        category: str | None,
    ) -> ScopedFilters:
        return ScopedFilters(
            wing=normalized_slug(agent_slug),
            room=validated_optional(room, self.allowed_rooms, "room"),
            category=validated_optional(category, self.allowed_categories, "category"),
        )


def _memory_row(
    *,
    memory_id: object,
    text: object,
    metadata: object,
) -> MemoryRow | None:
    if not isinstance(memory_id, str) or not isinstance(text, str):
        return None
    if not isinstance(metadata, dict):
        return None
    fields = _metadata_fields(metadata)
    if fields is None:
        return None
    return MemoryRow(memory_id=memory_id, text=text, **fields)


def _metadata_fields(metadata: dict[object, object]) -> dict[str, str] | None:
    values = {
        "wing": metadata.get("wing"),
        "room": metadata.get("room"),
        "category": metadata.get("category"),
        "created_at": metadata.get("created_at"),
    }
    if not _all_strings(values):
        return None
    return {key: value for key, value in values.items() if isinstance(value, str)}


def _all_strings(values: dict[str, object | None]) -> bool:
    return all(isinstance(value, str) for value in values.values())
