from __future__ import annotations

import json
from typing import Any

JSON_MAP = dict[str, Any]
ROUTE = tuple[str | None, str | None, str, str]


def normalize_optional_str(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def ensure_text(value: Any, *, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise RuntimeError(f"{field_name} is required")
    return normalized


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
