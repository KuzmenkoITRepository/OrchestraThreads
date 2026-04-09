from __future__ import annotations

from typing import Any, Literal

_TRUNCATION_SUFFIX = "..."


def required_text(value: Any, *, field_name: str) -> str:
    text = str(value or "").strip()
    if text:
        return text
    raise ValueError(f"{field_name} is required")


def bounded_text(value: Any, *, field_name: str, maximum: int) -> str:
    text = required_text(value, field_name=field_name)
    if len(text) <= maximum:
        return text
    raise ValueError(f"{field_name} must be at most {maximum} characters")


def bounded_text_with_truncation(
    value: Any,
    *,
    field_name: str,
    maximum: int,
) -> tuple[str, bool]:
    text = required_text(value, field_name=field_name)
    if len(text) <= maximum:
        return text, False
    return _truncate_text(text=text, maximum=maximum), True


def string_list(value: Any, *, minimum: int, maximum: int) -> list[str]:
    if value is None:
        items: list[str] = []
    elif isinstance(value, list):
        items = normalized_items(value)
    else:
        raise ValueError("value must be a list")
    if minimum <= len(items) <= maximum:
        return items
    raise ValueError(f"list size must be between {minimum} and {maximum}")


def final_status(value: Any) -> Literal["completed", "failed"] | None:
    normalized = str(value or "failed").strip() or "failed"
    if normalized == "completed":
        return "completed"
    if normalized == "failed":
        return "failed"
    return None


def normalized_items(value: list[Any]) -> list[str]:
    items: list[str] = []
    for item in value:
        normalized = str(item).strip()
        if normalized:
            items.append(normalized)
    return items


def _truncate_text(*, text: str, maximum: int) -> str:
    if maximum <= len(_TRUNCATION_SUFFIX):
        return text[:maximum]
    clipped = text[: maximum - len(_TRUNCATION_SUFFIX)].rstrip()
    return f"{clipped}{_TRUNCATION_SUFFIX}"
