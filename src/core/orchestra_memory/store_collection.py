from __future__ import annotations

import hashlib
from importlib import import_module
from pathlib import Path
from typing import Any, cast

from core.orchestra_memory.store_types import MempalaceClient, MempalaceCollection, MempalaceConfig

_READ_INCLUDE = ("documents", "metadatas")


def read_include() -> list[str]:
    return list(_READ_INCLUDE)


def create_collection(storage_path: Path) -> MempalaceCollection:
    client = _build_client(storage_path)
    config_module: Any = _store_import_module("mempalace.config")
    config = cast(MempalaceConfig, config_module.MempalaceConfig())
    return client.get_or_create_collection(config.collection_name)


def embedding_for_text(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values: list[float] = []
    for index in range(12):
        chunk = digest[index : index + 2]
        values.append(int.from_bytes(chunk, "big") / 255.0)
    return values


def _build_client(storage_path: Path) -> MempalaceClient:
    chromadb: Any = _store_import_module("chromadb")
    return cast(MempalaceClient, chromadb.PersistentClient(path=str(storage_path)))


def _store_import_module(module_name: str) -> object:
    store_module = import_module("core.orchestra_memory.store")
    return cast(object, store_module.import_module(module_name))
