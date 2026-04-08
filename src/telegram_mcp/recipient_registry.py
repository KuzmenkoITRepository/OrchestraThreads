"""Dynamic recipient registry with env fallback and optional file persistence."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from telegram_mcp.config_parsers import parse_chat_id

_ENV_PREFIX = "TELEGRAM_CHAT_ID_"
_REGISTRY_FILE_ENV = "TELEGRAM_RECIPIENTS_FILE"


@dataclass(frozen=True)
class Recipient:
    """A single recipient alias mapped to a Telegram chat ID."""

    alias: str
    chat_id: int


@dataclass
class RecipientRegistry:
    """Alias -> chat_id registry, extensible at runtime with optional file persistence."""

    _entries: dict[str, int] = field(default_factory=dict)
    _default_alias: str = "ivan"
    _persist_path: Path | None = None

    def resolve(self, alias: str | None) -> int:
        """Resolve an alias to a chat_id, falling back to default."""
        key = (alias or self._default_alias).strip().lower()
        chat_id = self._entries.get(key)
        if chat_id is None:
            raise ValueError(
                f"Unknown recipient alias '{key}'. Available: {self.available_aliases()}",
            )
        return chat_id

    def available_aliases(self) -> str:
        """Return a comma-separated string of registered aliases."""
        return ", ".join(sorted(self._entries)) or "(none)"

    def list_entries(self) -> dict[str, int]:
        """Return a copy of the alias -> chat_id mapping."""
        return dict(self._entries)

    def register(self, alias: str, chat_id: int) -> None:
        """Add or overwrite a recipient entry and persist if configured."""
        self._entries[alias.strip().lower()] = chat_id
        self._save()

    def unregister(self, alias: str) -> bool:
        """Remove a recipient. Returns True if it existed."""
        removed = self._entries.pop(alias.strip().lower(), None) is not None
        if removed:
            self._save()
        return removed

    @property
    def default_alias(self) -> str:
        """Return the default recipient alias."""
        return self._default_alias

    def _save(self) -> None:
        if self._persist_path is None:
            return
        self._persist_path.write_text(
            json.dumps(self._entries, indent=2, ensure_ascii=False),
        )


def load_recipients_from_env() -> RecipientRegistry:
    """Load recipients from env vars and optional JSON file."""
    default_alias = os.getenv("TELEGRAM_DEFAULT_RECIPIENT", "ivan").strip().lower()
    if not default_alias:
        raise ValueError("TELEGRAM_DEFAULT_RECIPIENT must not be empty")
    persist_path = _resolve_persist_path()
    registry = RecipientRegistry(
        _default_alias=default_alias,
        _persist_path=persist_path,
    )
    _load_from_file(registry, persist_path)
    _load_from_env(registry)
    return registry


def _resolve_persist_path() -> Path | None:
    raw = os.getenv(_REGISTRY_FILE_ENV, "").strip()
    if raw:
        return Path(raw)
    return None


def _load_from_file(registry: RecipientRegistry, path: Path | None) -> None:
    if path is None or not path.exists():
        return
    raw = json.loads(path.read_text())
    if isinstance(raw, dict):
        for alias, cid in raw.items():
            registry._entries[str(alias).strip().lower()] = int(cid)


def _load_from_env(registry: RecipientRegistry) -> None:
    for key, raw_value in os.environ.items():
        if not key.startswith(_ENV_PREFIX):
            continue
        alias = key.removeprefix(_ENV_PREFIX).strip().lower()
        if alias:
            registry._entries[alias] = parse_chat_id(raw_value)
