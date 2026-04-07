from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

Metadata = dict[str, object]
StoredRow = tuple[str, Metadata]


class FakeCollection:
    def __init__(self) -> None:
        self._entries: dict[str, StoredRow] = {}

    def add(
        self,
        *,
        ids: list[str],
        documents: list[str],
        metadatas: list[Metadata],
        embeddings: list[list[float]],
    ) -> None:
        if len(embeddings) != len(ids):
            raise AssertionError("embeddings must align with ids")
        for memory_id, document, metadata in zip(ids, documents, metadatas, strict=True):
            self._entries[memory_id] = (document, metadata)

    def get(
        self,
        *,
        ids: list[str] | None = None,
        where: dict[str, object] | None = None,
        include: list[str],
    ) -> dict[str, object]:
        rows = [
            (memory_id, document, metadata)
            for memory_id, (document, metadata) in self._entries.items()
            if self._matches(memory_id=memory_id, metadata=metadata, ids=ids, where=where)
        ]
        documents = [entry[1] for entry in rows] if "documents" in include else []
        metadatas = [entry[2] for entry in rows] if "metadatas" in include else []
        return {
            "ids": [entry[0] for entry in rows],
            "documents": documents,
            "metadatas": metadatas,
        }

    def delete(self, *, ids: list[str]) -> None:
        for memory_id in ids:
            self._entries.pop(memory_id, None)

    def _matches(
        self,
        *,
        memory_id: str,
        metadata: Metadata,
        ids: list[str] | None,
        where: dict[str, object] | None,
    ) -> bool:
        if ids is not None and memory_id not in ids:
            return False
        if where is None:
            return True
        return metadata_matches(metadata, where)


class PersistedCollection:
    def __init__(self, *, collection: FakeCollection, state_file: Path) -> None:
        self._collection = collection
        self._state_file = state_file

    def add(
        self,
        *,
        ids: list[str],
        documents: list[str],
        metadatas: list[Metadata],
        embeddings: list[list[float]],
    ) -> None:
        self._collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )
        self._write_state()

    def get(
        self,
        *,
        ids: list[str] | None = None,
        where: dict[str, object] | None = None,
        include: list[str],
    ) -> dict[str, object]:
        return self._collection.get(ids=ids, where=where, include=include)

    def delete(self, *, ids: list[str]) -> None:
        self._collection.delete(ids=ids)
        self._write_state()

    def _write_state(self) -> None:
        payload = {
            memory_id: {"text": row[0], "metadata": row[1]}
            for memory_id, row in self._collection._entries.items()
        }
        self._state_file.write_text(
            json.dumps({"entries": payload}, sort_keys=True),
            encoding="utf-8",
        )


class FakeClient:
    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._path.mkdir(parents=True, exist_ok=True)

    def get_or_create_collection(self, _name: str) -> PersistedCollection:
        collection = FakeCollection()
        state_file = self._path / "fake_state.json"
        if state_file.exists():
            self._restore_entries(collection, state_file)
        return PersistedCollection(collection=collection, state_file=state_file)

    def _restore_entries(self, collection: FakeCollection, state_file: Path) -> None:
        payload = json.loads(state_file.read_text(encoding="utf-8"))
        entries = payload.get("entries", {})
        if not isinstance(entries, dict):
            return
        for memory_id, row in entries.items():
            restored = _restored_row(memory_id=memory_id, row=row)
            if restored is not None:
                collection._entries[restored[0]] = restored[1]


def metadata_matches(metadata: Metadata, where: dict[str, object]) -> bool:
    and_clause = where.get("$and")
    if isinstance(and_clause, list):
        return all(
            metadata_matches(metadata, item) for item in and_clause if isinstance(item, dict)
        )
    return all(metadata.get(key) == value for key, value in where.items() if key != "$and")


def fake_import_module(name: str) -> Any:
    if name == "mempalace.config":
        return SimpleNamespace(MempalaceConfig=_fake_mempalace_config)
    if name == "chromadb":
        return SimpleNamespace(PersistentClient=FakeClient)
    raise ValueError(f"Unexpected import: {name}")


def _fake_mempalace_config() -> Any:
    return SimpleNamespace(collection_name="mempalace_drawers")


def _restored_row(memory_id: object, row: object) -> tuple[str, StoredRow] | None:
    if not isinstance(memory_id, str):
        return None
    if not isinstance(row, dict):
        return None
    text = row.get("text")
    metadata = row.get("metadata")
    if not isinstance(text, str) or not isinstance(metadata, dict):
        return None
    return memory_id, (text, metadata)
