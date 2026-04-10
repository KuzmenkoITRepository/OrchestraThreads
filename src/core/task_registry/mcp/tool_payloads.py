from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

JsonDict = dict[str, Any]


def json_default(serializable_value: Any) -> Any:
    if isinstance(serializable_value, UUID):
        return str(serializable_value)
    if isinstance(serializable_value, datetime):
        return serializable_value.isoformat()
    object_type = type(serializable_value).__name__
    raise TypeError(f"Object of type {object_type} is not JSON serializable")


def text_result(payload: JsonDict) -> JsonDict:
    return {
        "content": [
            {"type": "text", "text": json.dumps(payload, ensure_ascii=False, default=json_default)}
        ]
    }
