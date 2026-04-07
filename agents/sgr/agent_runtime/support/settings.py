"""SGR runtime settings and value normalization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def normalize_optional_str(value: Any) -> str | None:
    """Normalize value to optional stripped string."""
    normalized = str(value or "").strip()
    return normalized or None


def normalize_int(value: Any, *, default: int, minimum: int = 1) -> int:
    """Normalize value to integer with bounds."""
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    return max(minimum, int(text))


@dataclass(frozen=True)
class SGRRuntimeSettings:
    """Runtime settings for the SGR agent backend."""

    react_to_inactive: bool
    max_reasoning_steps: int
    max_direct_text_retries: int
