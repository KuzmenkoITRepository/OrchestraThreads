from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import cast

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
        payload_module = import_module("core.orchestra_memory.store_rows_payload")
        return cast(
            list[MemoryItem],
            payload_module.match_payload(payload=payload, query=self.query, limit=self.limit),
        )


@dataclass(frozen=True)
class StoreRules:
    allowed_rooms: set[str]
    allowed_categories: set[str]

    def build_item(self, *, agent_slug: str, room: str, category: str, text: str) -> MemoryItem:
        rules_module = import_module("core.orchestra_memory.store_rows_rules")
        return cast(
            MemoryItem,
            rules_module.build_item(
                agent_slug=agent_slug,
                room=room,
                category=category,
                text=text,
                rules=self._rule_sets(),
            ),
        )

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
        rules_module = import_module("core.orchestra_memory.store_rows_rules")
        return SearchRequest(
            filters=self.scoped_filters(agent_slug=agent_slug, room=room, category=category),
            query=cast(str, rules_module.normalized_query(query)),
            limit=cast(int, rules_module.validated_search_limit(limit)),
        )

    def scoped_filters(
        self,
        *,
        agent_slug: str,
        room: str | None,
        category: str | None,
    ) -> ScopedFilters:
        rules_module = import_module("core.orchestra_memory.store_rows_rules")
        values = cast(
            dict[str, str | None],
            rules_module.build_scoped_values(
                agent_slug=agent_slug,
                room=room,
                category=category,
                rules=self._rule_sets(),
            ),
        )
        wing = cast(str, values["wing"])
        return ScopedFilters(
            wing=wing,
            room=values["room"],
            category=values["category"],
        )

    def _rule_sets(self) -> object:
        rules_module = import_module("core.orchestra_memory.store_rows_rules")
        return cast(
            object,
            rules_module.RuleSets(
                allowed_rooms=self.allowed_rooms,
                allowed_categories=self.allowed_categories,
            ),
        )
