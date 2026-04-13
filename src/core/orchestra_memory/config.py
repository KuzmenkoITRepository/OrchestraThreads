from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_HOST = "0.0.0.0"
_DEFAULT_PORT = "8793"
_DEFAULT_STORAGE_PATH = "/tmp/orchestra_memory/palace"


@dataclass(frozen=True)
class OrchestraMemoryConfig:
    host: str
    port: int
    storage_path: Path


def load_config() -> OrchestraMemoryConfig:
    host = _required_text("ORCHESTRA_MEMORY_HOST", _DEFAULT_HOST)
    port = int(_required_text("ORCHESTRA_MEMORY_PORT", _DEFAULT_PORT))
    storage_path = Path(_required_text("ORCHESTRA_MEMORY_STORAGE_PATH", _DEFAULT_STORAGE_PATH))
    return OrchestraMemoryConfig(
        host=host,
        port=port,
        storage_path=storage_path,
    )


def _required_text(key: str, default: str) -> str:
    value = os.getenv(key, default).strip()
    if not value:
        raise ValueError(f"{key} must not be empty")
    return value
