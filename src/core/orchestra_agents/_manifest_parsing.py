from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.orchestra_agents._backend_validation import is_known_backend, validate_backend_config
from core.orchestra_agents._manifest_field_parsing import (
    _detect_mount_type,
    _FieldParsers,
    _merge_runtime_env,
    _parse_mounts_list,
    _validate_driver,
)
from core.orchestra_agents.errors import ManifestValidationError

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParsedManifest:
    slug: str
    display_name: str
    status: str
    agent: dict[str, Any]
    runtime: dict[str, Any]
    backend: dict[str, Any]
    manifest_path: Path | None
    auto_start: bool


class _LegacyNormalizer:
    @staticmethod
    def normalize(raw: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(raw)
        agent = dict(normalized.get("agent") or {})
        runtime = dict(normalized.get("runtime") or {})
        backend = dict(normalized.get("backend") or {})

        _LegacyNormalizer._migrate_agent_fields(normalized, agent)
        _LegacyNormalizer._migrate_backend_type(normalized, backend)
        _LegacyNormalizer._migrate_legacy_container(normalized, runtime)

        runtime.setdefault("driver", "docker")
        normalized["agent"] = agent
        normalized["runtime"] = runtime
        normalized["backend"] = backend
        return normalized

    @staticmethod
    def _migrate_agent_fields(normalized: dict[str, Any], agent: dict[str, Any]) -> None:
        for source_key in ("working_dir", "http_endpoint", "system_prompt_file"):
            if source_key in normalized and source_key not in agent:
                agent[source_key] = normalized.get(source_key)

    @staticmethod
    def _migrate_backend_type(normalized: dict[str, Any], backend: dict[str, Any]) -> None:
        if "backend_type" in normalized and "type" not in backend:
            backend["type"] = normalized.get("backend_type")

    @staticmethod
    def _migrate_legacy_container(normalized: dict[str, Any], runtime: dict[str, Any]) -> None:
        legacy_container = normalized.get("container")
        if not isinstance(legacy_container, dict):
            return
        _LegacyNormalizer._copy_container_fields(legacy_container, runtime)
        if "volumes" in legacy_container and "mounts" not in runtime:
            runtime["mounts"] = _LegacyNormalizer._convert_legacy_volumes(legacy_container)

    @staticmethod
    def _copy_container_fields(container: dict[str, Any], runtime: dict[str, Any]) -> None:
        for source_key, target_key in (
            ("image", "image"),
            ("entrypoint", "entrypoint"),
            ("command", "command"),
            ("extra_env", "env"),
            ("env_passthrough", "env_passthrough"),
        ):
            if source_key in container and target_key not in runtime:
                runtime[target_key] = container.get(source_key)

    @staticmethod
    def _convert_legacy_volumes(container: dict[str, Any]) -> list[dict[str, Any]]:
        normalized_mounts: list[dict[str, Any]] = []
        for item in container.get("volumes") or []:
            if not isinstance(item, dict):
                continue
            normalized_mounts.append(
                {
                    "type": _detect_mount_type(str(item.get("source") or "")),
                    "source": item.get("source"),
                    "target": item.get("target"),
                    "mode": "ro" if bool(item.get("read_only")) else "rw",
                }
            )
        return normalized_mounts


class _ManifestParser:
    def __init__(self, raw: dict[str, Any], *, manifest_path: Path | None = None) -> None:
        if not isinstance(raw, dict):
            raise ManifestValidationError(["manifest root must be an object"])
        self.raw = raw
        self.manifest_path = manifest_path
        self.errors: list[str] = []
        self._backend_type: str = ""

    def parse(self) -> ParsedManifest:
        normalized = self._normalize_legacy()
        self._backend_type = _extract_backend_type(normalized)
        status = _FieldParsers.as_string(
            normalized.get("status", "active"),
            "status",
            errors=self.errors,
        )
        if status and status.lower() not in {"active", "inactive"}:
            self.errors.append("status must be active or inactive")
        parsed = ParsedManifest(
            slug=_FieldParsers.as_string(normalized.get("slug"), "slug", errors=self.errors),
            display_name=_FieldParsers.as_string(
                normalized.get("display_name"),
                "display_name",
                errors=self.errors,
            ),
            status=status.lower(),
            agent=self._parse_agent(normalized.get("agent")),
            runtime=self._parse_runtime(normalized.get("runtime")),
            backend=self._parse_backend(normalized.get("backend")),
            manifest_path=self.manifest_path,
            auto_start=_FieldParsers.as_bool(
                normalized.get("auto_start"),
                "auto_start",
                errors=self.errors,
            ),
        )
        if self.errors:
            raise ManifestValidationError(self.errors)
        return parsed

    def _parse_agent(self, raw: Any) -> dict[str, Any]:
        agent_raw = _FieldParsers.as_dict(raw, "agent", errors=self.errors)
        system_prompt_file = str(agent_raw.get("system_prompt_file") or "").strip() or None
        allowed_peer_agent_slugs = _FieldParsers.allowed_peers(
            agent_raw.get("allowed_peer_agent_slugs"),
            errors=self.errors,
        )
        return {
            "working_dir": _FieldParsers.as_string(
                agent_raw.get("working_dir", "/workspace"),
                "agent.working_dir",
                errors=self.errors,
            ),
            "http_endpoint": _FieldParsers.as_string(
                agent_raw.get("http_endpoint"),
                "agent.http_endpoint",
                errors=self.errors,
            ),
            "system_prompt_file": system_prompt_file,
            "allowed_peer_agent_slugs": allowed_peer_agent_slugs,
        }

    def _parse_runtime(self, raw: Any) -> dict[str, Any]:
        runtime_raw = _FieldParsers.as_dict(raw, "runtime", errors=self.errors)
        image_required = not is_known_backend(self._backend_type)
        runtime_payload: dict[str, Any] = {
            "driver": _FieldParsers.as_string(
                runtime_raw.get("driver", "docker"),
                "runtime.driver",
                errors=self.errors,
            ).lower(),
            "image": _FieldParsers.as_string(
                runtime_raw.get("image"),
                "runtime.image",
                errors=self.errors,
                required=image_required,
            ),
            "entrypoint": str(runtime_raw.get("entrypoint") or "").strip() or None,
            "command": _FieldParsers.as_command(
                runtime_raw.get("command"),
                "runtime.command",
                errors=self.errors,
            ),
            "mounts": _parse_mounts_list(runtime_raw.get("mounts"), errors=self.errors),
        }
        _validate_driver(runtime_payload, errors=self.errors)
        _merge_runtime_env(runtime_payload, runtime_raw, errors=self.errors)
        return runtime_payload

    def _parse_backend(self, raw: Any) -> dict[str, Any]:
        backend_raw = _FieldParsers.as_dict(raw, "backend", errors=self.errors)
        backend_config = backend_raw.get("config") or {}
        if not isinstance(backend_config, dict):
            self.errors.append("backend.config must be an object")
            backend_config = {}
        backend_type = _FieldParsers.as_string(
            backend_raw.get("type"),
            "backend.type",
            errors=self.errors,
        )
        validate_backend_config(
            backend_type,
            dict(backend_config),
            errors=self.errors,
        )
        return {
            "type": backend_type,
            "config": backend_config,
        }

    def _normalize_legacy(self) -> dict[str, Any]:
        return _LegacyNormalizer.normalize(self.raw)


def _extract_backend_type(normalized: dict[str, Any]) -> str:
    """Extract backend type string from a normalized manifest dict."""
    backend_raw = normalized.get("backend")
    if not isinstance(backend_raw, dict):
        return ""
    return str(backend_raw.get("type") or "").strip()
