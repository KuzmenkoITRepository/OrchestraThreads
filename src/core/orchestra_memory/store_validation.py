from __future__ import annotations


def required_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def normalized_slug(agent_slug: str) -> str:
    return required_text(agent_slug, "agent_slug")


def validated_limit(limit: int) -> int:
    if limit < 1:
        raise ValueError("limit must be >= 1")
    return min(limit, 100)
