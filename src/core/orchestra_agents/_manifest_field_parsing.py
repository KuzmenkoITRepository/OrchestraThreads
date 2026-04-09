"""Value and runtime field parsing helpers for manifests."""

from __future__ import annotations

import shlex
from typing import Any


def _detect_mount_type(source: str) -> str:
    normalized = str(source).strip()
    if normalized.startswith("/") or normalized.startswith("."):
        return "bind"
    return "volume"


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
    def as_bool(
        value: Any,
        field_name: str,
        *,
        errors: list[str],
        default: bool = False,
    ) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        errors.append(f"{field_name} must be a boolean")
        return default

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
            command: list[str] = []
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


def _validate_driver(
    runtime_payload: dict[str, Any],
    *,
    errors: list[str],
) -> None:
    runtime_driver = str(runtime_payload["driver"] or "")
    if runtime_driver and runtime_driver != "docker":
        errors.append("runtime.driver must be docker in v1")


def _merge_runtime_env(
    runtime_payload: dict[str, Any],
    runtime_raw: dict[str, Any],
    *,
    errors: list[str],
) -> None:
    env, env_passthrough = _EnvParser.parse(runtime_raw, errors=errors)
    runtime_payload["env"] = env
    runtime_payload["env_passthrough"] = env_passthrough


def _parse_mounts_list(raw: Any, *, errors: list[str]) -> list[dict[str, str]]:
    mounts_raw = raw or []
    if not isinstance(mounts_raw, list):
        errors.append("runtime.mounts must be a list")
        return []
    mounts: list[dict[str, str]] = []
    for index, item in enumerate(mounts_raw):
        mounts.append(_MountParser.parse(item, index, errors=errors))
    return mounts
