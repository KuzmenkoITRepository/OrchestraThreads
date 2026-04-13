"""SSE event parsing utilities."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def extract_data_lines(block: str) -> list[str]:
    """Extract data lines from SSE block."""
    lines = block.strip().split("\n")
    return [line[5:].strip() for line in lines if line.startswith("data:")]


def parse_sse_block(block: str) -> dict[str, Any] | None:
    """Parse a single SSE block into a dict payload."""
    data_lines = extract_data_lines(block)
    if not data_lines:
        return None
    return parse_json_safe("\n".join(data_lines))


def parse_json_safe(raw: str) -> dict[str, Any] | None:
    """Parse JSON string or return None on failure."""
    return _try_parse_json(raw)


def _try_parse_json(raw: str) -> dict[str, Any] | None:
    try:
        result = json.loads(raw)
    except (json.JSONDecodeError, KeyError) as exc:
        logger.warning("Failed to parse SSE event: %s", exc)
        return None
    return _validate_dict_result(result)


def _validate_dict_result(result: Any) -> dict[str, Any] | None:
    """Ensure result is a proper dict."""
    if isinstance(result, dict):
        return result
    return None
