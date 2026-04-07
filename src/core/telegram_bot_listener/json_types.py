from __future__ import annotations

from typing import TypeAlias

JsonValue: TypeAlias = object
JsonDict: TypeAlias = dict[str, object]


def cast_json_dict(value: object | None) -> JsonDict:
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    return {}


def cast_json_list(value: object | None) -> list[object]:
    if isinstance(value, list):
        return list(value)
    return []


def optional_text(value: object | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def parse_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        return int(value.strip())
    raise ValueError(f"Expected int-compatible value, got {value!r}")


def utc_now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(tz=UTC).isoformat()
