"""Backend-specific config validation for manifest parsing."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _MCPEntrySchema:
    backend_type: str
    required_keys: frozenset[str]
    optional_keys: frozenset[str]

    @property
    def known_keys(self) -> frozenset[str]:
        return self.required_keys | self.optional_keys


@dataclass(frozen=True)
class _BackendSchema:
    required_keys: frozenset[str]
    optional_keys: frozenset[str]
    mcp_entry_schema: _MCPEntrySchema | None = None
    http_mcp_entry_schema: _MCPEntrySchema | None = None

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
            mcp_entry_schema=_MCPEntrySchema(
                backend_type="sgr_minimax",
                required_keys=frozenset(("name", "module", "class")),
                optional_keys=frozenset(("schema_fn",)),
            ),
            http_mcp_entry_schema=_MCPEntrySchema(
                backend_type="sgr_minimax",
                required_keys=frozenset(("name", "transport", "url", "bearer_token")),
                optional_keys=frozenset(("enabled_tools", "timeout_seconds")),
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
            mcp_entry_schema=_MCPEntrySchema(
                backend_type="agent_mux",
                required_keys=frozenset(("name", "command")),
                optional_keys=frozenset(
                    (
                        "args",
                        "cwd",
                        "startup_timeout_sec",
                        "required",
                        "enabled",
                        "enabled_tools",
                        "env",
                    ),
                ),
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
            mcp_entry_schema=_MCPEntrySchema(
                backend_type="opencode_omo",
                required_keys=frozenset(("name", "command")),
                optional_keys=frozenset(("args", "env")),
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
    _validate_mcp_servers(config.get("mcp_servers"), errors=errors, schema=schema)


def _validate_mcp_servers(
    raw_servers: Any,
    *,
    errors: list[str],
    schema: _BackendSchema,
) -> None:
    if raw_servers is None:
        return
    if not isinstance(raw_servers, list):
        errors.append("backend.config.mcp_servers must be a list")
        return
    mcp_entry_schema = schema.mcp_entry_schema
    if mcp_entry_schema is None:
        return
    for index, raw_entry in enumerate(raw_servers):
        entry_schema = _select_mcp_entry_schema(raw_entry, schema)
        _validate_mcp_entry(index, raw_entry, errors, entry_schema)


def _select_mcp_entry_schema(
    raw_entry: Any,
    schema: _BackendSchema,
) -> _MCPEntrySchema:
    if not isinstance(raw_entry, dict):
        return schema.mcp_entry_schema or _MCPEntrySchema("", frozenset(), frozenset())
    if raw_entry.get("transport") != "http":
        return schema.mcp_entry_schema or _MCPEntrySchema("", frozenset(), frozenset())
    http_schema = schema.http_mcp_entry_schema
    if http_schema is None:
        return schema.mcp_entry_schema or _MCPEntrySchema("", frozenset(), frozenset())
    return http_schema


def _validate_mcp_entry(
    index: int,
    raw_entry: Any,
    errors: list[str],
    schema: _MCPEntrySchema,
) -> None:
    entry_path = f"backend.config.mcp_servers[{index}]"
    if not isinstance(raw_entry, dict):
        errors.append(f"{entry_path} must be an object")
        return
    for key in sorted(schema.required_keys):
        if key not in raw_entry:
            errors.append(
                f"{entry_path}.{key} is required for backend type '{schema.backend_type}'",
            )
    for key in sorted(raw_entry):
        if key not in schema.known_keys:
            errors.append(
                f"{entry_path}.{key} is not supported for backend type '{schema.backend_type}'",
            )
