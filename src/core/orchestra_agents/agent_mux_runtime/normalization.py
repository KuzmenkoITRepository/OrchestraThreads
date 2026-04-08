from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)


def normalize_bool(normalized_value: Any, *, default: bool = False) -> bool:
    if normalized_value is None:
        return default
    if isinstance(normalized_value, bool):
        return normalized_value
    return str(normalized_value).strip().lower() in {"1", "true", "yes", "on"}


def normalize_float(normalized_value: Any, *, default: float) -> float:
    if normalized_value is None:
        return default
    text = str(normalized_value).strip()
    if not text:
        return default
    return float(text)


def normalize_int(normalized_value: Any, *, default: int) -> int:
    if normalized_value is None:
        return default
    text = str(normalized_value).strip()
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


def normalize_mcp_servers(raw_servers: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_servers, list):
        return []
    normalized: list[dict[str, Any]] = []
    for server_item in raw_servers:
        server = _normalize_mcp_server(server_item)
        if server is None:
            continue
        normalized.append(server)
    return normalized


def _normalize_mcp_server(server_item: Any) -> dict[str, Any] | None:
    if not isinstance(server_item, Mapping):
        return None
    name = str(server_item.get("name") or "").strip()
    command = str(server_item.get("command") or "").strip()
    if not name or not command:
        return None
    return {str(key): server_item[key] for key in server_item}
