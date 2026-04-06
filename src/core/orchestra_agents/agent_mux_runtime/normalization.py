from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)


def normalize_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def normalize_float(value: Any, *, default: float) -> float:
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    return float(text)


def normalize_int(value: Any, *, default: int) -> int:
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    return int(text)


def message_preview(text: str, *, limit: int = 200) -> str:
    preview = " ".join(str(text or "").split())
    if len(preview) <= limit:
        return preview
    return f"{preview[: max(0, limit - 3)]}..."


def sanitize_reply_text(text: str) -> str:
    cleaned = _THINK_BLOCK_RE.sub("", str(text or ""))
    cleaned = cleaned.replace("<think>", "").replace("</think>", "")
    return cleaned.strip()


def normalize_mcp_servers(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in value:
        server = _normalize_mcp_server(item)
        if server is None:
            continue
        normalized.append(server)
    return normalized


def _normalize_mcp_server(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, Mapping):
        return None
    name = str(item.get("name") or "").strip()
    command = str(item.get("command") or "").strip()
    if not name or not command:
        return None
    return {str(key): item[key] for key in item}
