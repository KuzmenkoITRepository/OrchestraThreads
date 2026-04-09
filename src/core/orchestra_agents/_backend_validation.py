"""Backend-specific config validation for manifest parsing."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _BackendSchema:
    required_keys: frozenset[str]
    optional_keys: frozenset[str]

    @property
    def known_keys(self) -> frozenset[str]:
        return self.required_keys | self.optional_keys


_BACKEND_SCHEMAS = MappingProxyType(
    {
        "sgr_minimax": _BackendSchema(
            required_keys=frozenset(("route_policy", "model")),
            optional_keys=frozenset(
                (
                    "temperature",
                    "max_tokens",
                    "timeout_seconds",
                    "react_to_inactive",
                    "max_reasoning_steps",
                    "max_direct_text_retries",
                    "mcp_servers",
                )
            ),
        ),
        "agent_mux": _BackendSchema(
            required_keys=frozenset(("role", "llm_route_policy", "model")),
            optional_keys=frozenset(
                (
                    "artifact_root",
                    "timeout_seconds",
                    "require_tool_call_for_response",
                    "mcp_servers",
                )
            ),
        ),
        "opencode_omo": _BackendSchema(
            required_keys=frozenset(("model",)),
            optional_keys=frozenset(
                (
                    "opencode_serve_port",
                    "dispatch_timeout_seconds",
                    "startup_timeout_seconds",
                    "mcp_servers",
                )
            ),
        ),
    }
)


def is_known_backend(backend_type: str) -> bool:
    """Check whether the backend type is a known unified backend."""
    return backend_type in _BACKEND_SCHEMAS


def validate_backend_config(
    backend_type: str,
    config: dict[str, Any],
    *,
    errors: list[str],
) -> None:
    """Validate backend config against known unified schemas."""
    if not is_known_backend(backend_type):
        _logger.warning("backend.type '%s' is not a known unified backend", backend_type)
        return
    schema = _BACKEND_SCHEMAS[backend_type]
    for key in sorted(schema.required_keys):
        if key not in config:
            errors.append(
                f"backend.config.{key} is required for backend type '{backend_type}'",
            )
    for key in sorted(config):
        if key in schema.known_keys:
            continue
        _logger.warning(
            "backend.config.%s is not a known key for backend type '%s'",
            key,
            backend_type,
        )
