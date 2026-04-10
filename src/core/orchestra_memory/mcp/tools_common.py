from __future__ import annotations

import json
from typing import Any

JSON_MAP = dict[str, Any]


def normalize_optional_str(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def ensure_text(value: Any, *, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise RuntimeError(f"{field_name} is required")
    return normalized


def ensure_positive_int(value: Any, *, field_name: str, default: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise RuntimeError(f"{field_name} must be an integer") from None
    if parsed <= 0:
        raise RuntimeError(f"{field_name} must be greater than zero")
    return parsed


def result(payload: JSON_MAP, *, text: str | None = None) -> JSON_MAP:
    response_text = json.dumps(payload, ensure_ascii=False)
    if text is not None:
        response_text = text
    return {
        "structuredContent": payload,
        "content": [
            {
                "type": "text",
                "text": response_text,
            }
        ],
    }


def tool(name: str, description: str, input_schema: JSON_MAP) -> JSON_MAP:
    return {
        "name": name,
        "description": description,
        "inputSchema": input_schema,
    }
