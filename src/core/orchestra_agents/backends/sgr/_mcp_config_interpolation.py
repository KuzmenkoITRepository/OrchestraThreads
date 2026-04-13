"""Environment variable interpolation for MCP config values."""

from __future__ import annotations

import os
from typing import Any

_ENV_PLACEHOLDER = "{env."
_ENV_PREFIX_LEN = len("{env.")


def interpolate_config_values(raw_config: dict[str, Any]) -> dict[str, Any]:
    """Recursively interpolate {env.VAR} placeholders with environment values."""
    return {key: _interpolate_value(value) for key, value in raw_config.items()}


def _interpolate_value(value: Any) -> Any:
    """Interpolate a single config value."""
    if isinstance(value, str):
        return _maybe_render_env_placeholder(value)
    if isinstance(value, list):
        return [_interpolate_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _interpolate_value(val) for key, val in value.items()}
    return value


def _maybe_render_env_placeholder(text: str) -> str:
    """Render {env.VAR} placeholder if present, otherwise return text unchanged."""
    if _ENV_PLACEHOLDER in text:
        return _render_env_placeholder(text)
    return text


def _render_env_placeholder(text: str) -> str:
    """Render a single {env.VAR} placeholder."""
    if _is_env_placeholder(text):
        return _get_env_value(text, text)
    return text


def _is_env_placeholder(text: str) -> bool:
    """Check if text is a simple {env.VAR} placeholder."""
    return text.startswith(_ENV_PLACEHOLDER) and text.endswith("}")


def _get_env_value(fallback: str, text: str) -> str:
    """Get environment variable value or fail fast when missing."""
    var_name = text[_ENV_PREFIX_LEN:-1]
    value = os.environ.get(var_name)
    if value is None:
        raise ValueError(f"Missing required environment variable: {var_name}")
    return value
