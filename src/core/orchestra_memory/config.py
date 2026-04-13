from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_HOST = "0.0.0.0"
_DEFAULT_PORT = "8793"
_DEFAULT_STORAGE_PATH = "/tmp/orchestra_memory/palace"
_DEFAULT_ROOMS = "profile,knowledge,task,ivan,default,preferences,context,notes,facts,current,telegram,general,workspace"
_DEFAULT_CATEGORIES = "fact,preference,instruction"


@dataclass(frozen=True)
class OrchestraMemoryConfig:
    host: str
    port: int
    storage_path: Path
    allowed_rooms: tuple[str, ...]
    allowed_categories: tuple[str, ...]


def load_config() -> OrchestraMemoryConfig:
    host = _required_text("ORCHESTRA_MEMORY_HOST", _DEFAULT_HOST)
    port = int(_required_text("ORCHESTRA_MEMORY_PORT", _DEFAULT_PORT))
    storage_path = Path(_required_text("ORCHESTRA_MEMORY_STORAGE_PATH", _DEFAULT_STORAGE_PATH))
    allowed_rooms = _split_csv(_required_text("ORCHESTRA_MEMORY_ALLOWED_ROOMS", _DEFAULT_ROOMS))
    allowed_categories = _split_csv(
        _required_text("ORCHESTRA_MEMORY_ALLOWED_CATEGORIES", _DEFAULT_CATEGORIES),
    )
    return OrchestraMemoryConfig(
        host=host,
        port=port,
        storage_path=storage_path,
        allowed_rooms=allowed_rooms,
        allowed_categories=allowed_categories,
    )


def _required_text(key: str, default: str) -> str:
    value = os.getenv(key, default).strip()
    if not value:
        raise ValueError(f"{key} must not be empty")
    return value


def _split_csv(value: str) -> tuple[str, ...]:
    items: list[str] = []
    for raw_item in value.split(","):
        item = raw_item.strip()
        if item:
            items.append(item)
    if not items:
        raise ValueError("Comma-separated value must not be empty")
    return tuple(items)
