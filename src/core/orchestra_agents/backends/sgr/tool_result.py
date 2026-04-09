from __future__ import annotations

import json
from typing import Any


def result_text(mcp_result: dict[str, Any]) -> str:
    flattened = flatten_content(mcp_result.get("content"))
    if flattened:
        return flattened
    return json.dumps(mcp_result, ensure_ascii=False)


def structured_content(mcp_result: dict[str, Any]) -> dict[str, Any]:
    content = mcp_result.get("structuredContent")
    if isinstance(content, dict):
        return content
    return {}


def flatten_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return _flatten_list(content)
    if isinstance(content, dict):
        text = content.get("text")
        if text is not None:
            return str(text)
    return str(content)


def _flatten_list(content: list[Any]) -> str:
    parts: list[str] = []
    for item in content:
        parts.append(_flatten_item(item))
    return "".join(parts)


def _flatten_item(item: Any) -> str:
    if not isinstance(item, dict):
        return str(item)
    text = item.get("text")
    if text is not None:
        return str(text)
    return str(item)
