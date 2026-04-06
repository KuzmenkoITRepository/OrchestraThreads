from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def sanitize_fragment(value: str) -> str:
    sanitized_chars: list[str] = []
    for char in str(value or "").strip():
        sanitized_chars.append(_sanitized_char(char))
    text = "".join(sanitized_chars)
    return text.strip("._") or "item"


def _sanitized_char(char: str) -> str:
    if char.isalnum() or char in {"-", "_", "."}:
        return char
    return "_"


def short_context_id() -> str:
    return uuid.uuid4().hex[:12]


def normalize_recent_entries(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    entries: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        entries.append({str(key): item[key] for key in item})
    return entries


@dataclass(frozen=True)
class RuntimeStatePaths:
    root: Path
    queue_dir: Path
    processing_dir: Path
    failed_dir: Path
    artifacts_dir: Path
    meta_dir: Path
    home_dir: Path
    active_context_path: Path
    handled_file: Path
    active_file: Path
    counter_file: Path
    context_file: Path

    @classmethod
    def from_root_dir(cls, root_dir: str) -> RuntimeStatePaths:
        root = Path(root_dir).expanduser().resolve()
        meta_dir = root / "meta"
        return cls(
            root=root,
            queue_dir=root / "queue",
            processing_dir=root / "processing",
            failed_dir=root / "failed",
            artifacts_dir=root / "artifacts",
            meta_dir=meta_dir,
            home_dir=root / "home",
            active_context_path=root / "active_context.json",
            handled_file=meta_dir / "handled_events.json",
            active_file=meta_dir / "active_dispatches.json",
            counter_file=meta_dir / "queue_counter.json",
            context_file=meta_dir / "context.json",
        )

    def ensure_layout(self) -> None:
        for path in (
            self.root,
            self.queue_dir,
            self.processing_dir,
            self.failed_dir,
            self.artifacts_dir,
            self.meta_dir,
            self.home_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
