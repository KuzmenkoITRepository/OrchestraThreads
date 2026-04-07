from __future__ import annotations

from typing import Protocol


class MempalaceCollection(Protocol):
    def add(
        self,
        *,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, object]],
        embeddings: list[list[float]],
    ) -> None: ...

    def get(
        self,
        *,
        ids: list[str] | None = None,
        where: dict[str, object] | None = None,
        include: list[str],
    ) -> dict[str, object]: ...

    def delete(self, *, ids: list[str]) -> None: ...


class MempalaceClient(Protocol):
    def get_or_create_collection(self, name: str) -> MempalaceCollection: ...


class MempalaceConfig(Protocol):
    collection_name: str
