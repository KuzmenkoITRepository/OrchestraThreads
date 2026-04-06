from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_active_context(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(path)


def clear_active_context(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return


def process_matches_filters(
    payload: dict[str, Any] | None,
    *,
    thread_id: str | None,
    parent_thread_id: str | None,
) -> bool:
    active_payload = payload or {}
    normalized_thread_id = str(thread_id or "").strip()
    if (
        normalized_thread_id
        and str(active_payload.get("thread_id") or "").strip() == normalized_thread_id
    ):
        return True
    normalized_parent_thread_id = str(parent_thread_id or "").strip()
    if (
        normalized_parent_thread_id
        and str(active_payload.get("parent_thread_id") or "").strip() == normalized_parent_thread_id
    ):
        return True
    return False
