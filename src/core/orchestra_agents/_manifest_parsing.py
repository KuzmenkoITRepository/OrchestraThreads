from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.orchestra_agents.errors import ManifestValidationError


def _detect_mount_type(source: str) -> str:
    normalized = str(source).strip()
    if normalized.startswith("/") or normalized.startswith("."):
        return "bind"
    return "volume"


@dataclass(frozen=True)
class ParsedManifest:
    slug: str
    display_name: str
    status: str
    agent: dict[str, Any]
    runtime: dict[str, Any]
    backend: dict[str, Any]
    manifest_path: Path | None


class _FieldParsers:
    @staticmethod
    def as_dict(value: Any, field_name: str, *, errors: list[str]) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            errors.append(f"{field_name} must be an object")
            return {}
        return dict(value)

    @staticmethod
    def as_string(
        value: Any,
        field_name: str,
        *,
        errors: list[str],
        required: bool = True,
    ) -> str:
        if value is None:
            if required:
                errors.append(f"{field_name} is required")
            return ""
        normalized = str(value).strip()
        if required and not normalized:
            errors.append(f"{field_name} is required")
        return normalized

    @staticmethod
    def as_command(value: Any, field_name: str, *, errors: list[str]) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [item for item in shlex.split(value) if item]
        if isinstance(value, list):
            command = []
            for index, item in enumerate(value):
                normalized = str(item).strip()
                if not normalized:
                    errors.append(f"{field_name}[{index}] must not be empty")
                    continue
                command.append(normalized)
            return command
        errors.append(f"{field_name} must be a string or list of strings")
        return []

    @staticmethod
    def allowed_peers(raw: Any, *, errors: list[str]) -> list[str]:
        if raw is None:
            return []
        if not isinstance(raw, list):
            errors.append("agent.allowed_peer_agent_slugs must be a list")
            return []
        allowed: list[str] = []
        for index, item in enumerate(raw):
            slug = str(item or "").strip()
            if not slug:
                errors.append(f"agent.allowed_peer_agent_slugs[{index}] must not be empty")
                continue
            allowed.append(slug)
        return allowed


class _EnvParser:
    @staticmethod
    def parse(
        runtime_raw: dict[str, Any], *, errors: list[str]
    ) -> tuple[dict[str, str], list[str]]:
        env = _EnvParser._parse_env(runtime_raw.get("env"), errors=errors)
        env_passthrough = _EnvParser._parse_env_passthrough(
            runtime_raw.get("env_passthrough"),
            errors=errors,
        )
        return env, env_passthrough

    @staticmethod
    def _parse_env(raw_value: Any, *, errors: list[str]) -> dict[str, str]:
        env_raw = raw_value or {}
        if not isinstance(env_raw, dict):
            errors.append("runtime.env must be an object")
            return {}
        env: dict[str, str] = {}
        for key, value in env_raw.items():
            normalized_key = str(key).strip()
            if normalized_key:
                env[normalized_key] = str(value)
        return env

    @staticmethod
    def _parse_env_passthrough(raw_value: Any, *, errors: list[str]) -> list[str]:
        passthrough_raw = raw_value or []
        if not isinstance(passthrough_raw, list):
            errors.append("runtime.env_passthrough must be a list")
            return []
        env_passthrough: list[str] = []
        for item in passthrough_raw:
            normalized = str(item).strip()
            if normalized:
                env_passthrough.append(normalized)
        return env_passthrough


class _MountParser:
    @staticmethod
    def parse(raw: Any, index: int, *, errors: list[str]) -> dict[str, str]:
        mount_raw = _FieldParsers.as_dict(raw, f"runtime.mounts[{index}]", errors=errors)
        mount_type = _FieldParsers.as_string(
            mount_raw.get("type", _detect_mount_type(str(mount_raw.get("source") or ""))),
            f"runtime.mounts[{index}].type",
            errors=errors,
        ).lower()
        if mount_type not in {"bind", "volume"}:
            errors.append(f"runtime.mounts[{index}].type must be bind or volume")
        mount_mode = _FieldParsers.as_string(
            mount_raw.get("mode", "rw"),
            f"runtime.mounts[{index}].mode",
            errors=errors,
        ).lower()
        if mount_mode not in {"rw", "ro"}:
            errors.append(f"runtime.mounts[{index}].mode must be rw or ro")
        return {
            "type": mount_type or "bind",
            "source": _FieldParsers.as_string(
                mount_raw.get("source"),
                f"runtime.mounts[{index}].source",
                errors=errors,
            ),
            "target": _FieldParsers.as_string(
                mount_raw.get("target"),
                f"runtime.mounts[{index}].target",
                errors=errors,
            ),
            "mode": mount_mode or "rw",
        }


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

    def parse(self) -> ParsedManifest:
        normalized = self._normalize_legacy()
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
            ),
            "entrypoint": str(runtime_raw.get("entrypoint") or "").strip() or None,
            "command": _FieldParsers.as_command(
                runtime_raw.get("command"),
                "runtime.command",
                errors=self.errors,
            ),
            "mounts": self._parse_mounts(runtime_raw.get("mounts")),
        }
        runtime_driver = str(runtime_payload["driver"] or "")
        if runtime_driver and runtime_driver != "docker":
            self.errors.append("runtime.driver must be docker in v1")
        env, env_passthrough = _EnvParser.parse(runtime_raw, errors=self.errors)
        runtime_payload["env"] = env
        runtime_payload["env_passthrough"] = env_passthrough
        return runtime_payload

    def _parse_mounts(self, raw: Any) -> list[dict[str, str]]:
        mounts_raw = raw or []
        if isinstance(mounts_raw, list):
            mounts: list[dict[str, str]] = []
            for index, item in enumerate(mounts_raw):
                mounts.append(_MountParser.parse(item, index, errors=self.errors))
            return mounts
        self.errors.append("runtime.mounts must be a list")
        return []

    def _parse_backend(self, raw: Any) -> dict[str, Any]:
        backend_raw = _FieldParsers.as_dict(raw, "backend", errors=self.errors)
        backend_config = backend_raw.get("config") or {}
        if not isinstance(backend_config, dict):
            self.errors.append("backend.config must be an object")
            backend_config = {}
        return {
            "type": _FieldParsers.as_string(
                backend_raw.get("type"),
                "backend.type",
                errors=self.errors,
            ),
            "config": backend_config,
        }

    def _normalize_legacy(self) -> dict[str, Any]:
        return _LegacyNormalizer.normalize(self.raw)
