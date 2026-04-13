from __future__ import annotations

from collections.abc import Iterator

MemoryItem = dict[str, str]
StorePayload = dict[str, object]


def match_payload(*, payload: StorePayload, query: str, limit: int) -> list[MemoryItem]:
    return _PayloadRows(payload).match(query=query, limit=limit)


class _PayloadRows:
    def __init__(self, payload: StorePayload) -> None:
        self._payload = payload

    def match(self, *, query: str, limit: int) -> list[MemoryItem]:
        items = list(reversed(self._items()))
        matched = [item for item in items if self._matches_query(item=item, query=query)]
        return matched[:limit]

    def _items(self) -> list[MemoryItem]:
        result: list[MemoryItem] = []
        for memory_id, text, metadata in self._rows():
            item = self._memory_row(memory_id=memory_id, text=text, metadata=metadata)
            if item is not None:
                result.append(item)
        return result

    def _rows(self) -> Iterator[tuple[object, object, object]]:
        ids = self._payload_list("ids")
        documents = self._payload_list("documents")
        metadatas = self._payload_list("metadatas")
        max_len = max(len(ids), len(documents), len(metadatas))
        for i in range(max_len):
            yield (
                ids[i] if i < len(ids) else None,
                documents[i] if i < len(documents) else None,
                metadatas[i] if i < len(metadatas) else {},
            )

    def _payload_list(self, key: str) -> list[object]:
        value = self._payload.get(key, [])
        return value if isinstance(value, list) else []

    @staticmethod
    def _matches_query(*, item: MemoryItem, query: str) -> bool:
        if not query:
            return True
        return query in item["text"].lower()

    @staticmethod
    def _memory_row(
        *,
        memory_id: object,
        text: object,
        metadata: object,
    ) -> MemoryItem | None:
        if not isinstance(memory_id, str) or not isinstance(text, str):
            return None
        if not isinstance(metadata, dict):
            return None
        fields = _metadata_fields(metadata)
        if fields is None:
            return None
        return {
            "memory_id": memory_id,
            "agent_slug": fields["wing"],
            "room": fields["room"],
            "category": fields["category"],
            "text": text,
            "created_at": fields["created_at"],
        }


def _metadata_fields(metadata: dict[object, object]) -> dict[str, str] | None:
    values = {
        "wing": metadata.get("wing"),
        "room": metadata.get("room"),
        "category": metadata.get("category"),
        "created_at": metadata.get("created_at"),
    }
    if not all(isinstance(value, str) for value in values.values()):
        return None
    return {key: value for key, value in values.items() if isinstance(value, str)}
