"""Manifest schema for orchestra_agents."""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .errors import ManifestValidationError


def _as_dict(value: Any, field_name: str, *, errors: list[str]) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        errors.append(f"{field_name} must be an object")
        return {}
    return dict(value)


def _as_string(value: Any, field_name: str, *, errors: list[str], required: bool = True) -> str:
    if value is None:
        if required:
            errors.append(f"{field_name} is required")
        return ""
    normalized = str(value).strip()
    if required and not normalized:
        errors.append(f"{field_name} is required")
    return normalized


def _as_command(value: Any, field_name: str, *, errors: list[str]) -> list[str]:
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


def _detect_mount_type(source: str) -> str:
    normalized = str(source).strip()
    if normalized.startswith("/") or normalized.startswith("."):
        return "bind"
    return "volume"


@dataclass(frozen=True)
class AgentConfig:
    """Logical agent contract fields."""

    working_dir: str
    http_endpoint: str
    system_prompt_file: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "working_dir": self.working_dir,
            "http_endpoint": self.http_endpoint,
            "system_prompt_file": self.system_prompt_file,
        }


@dataclass(frozen=True)
class RuntimeMount:
    """Container mount entry."""

    type: str
    source: str
    target: str
    mode: str = "rw"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "source": self.source,
            "target": self.target,
            "mode": self.mode,
        }


@dataclass(frozen=True)
class RuntimeConfig:
    """Runtime launch configuration."""

    driver: str
    image: str
    entrypoint: str | None = None
    command: list[str] = field(default_factory=list)
    mounts: list[RuntimeMount] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    env_passthrough: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "driver": self.driver,
            "image": self.image,
            "entrypoint": self.entrypoint,
            "command": list(self.command),
            "mounts": [item.to_dict() for item in self.mounts],
            "env": dict(self.env),
            "env_passthrough": list(self.env_passthrough),
        }


@dataclass(frozen=True)
class BackendConfig:
    """Backend selection and backend-specific config payload."""

    type: str
    config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "config": dict(self.config),
        }


@dataclass(frozen=True)
class AgentManifest:
    """Validated and normalized agent manifest."""

    slug: str
    display_name: str
    status: str
    agent: AgentConfig
    runtime: RuntimeConfig
    backend: BackendConfig
    manifest_path: Path | None = field(default=None, compare=False)

    @property
    def is_active(self) -> bool:
        return self.status.lower() == "active"

    def resolve_http_endpoint(self, *, container_name: str | None = None) -> str:
        values = {
            "slug": self.slug,
            "container_name": container_name or f"orchestra-agent-{self.slug}",
        }
        raw = self.agent.http_endpoint
        try:
            return raw.format(**values)
        except Exception:
            return raw

    def load_system_prompt(self) -> str:
        if not self.agent.system_prompt_file or self.manifest_path is None:
            return ""
        prompt_path = (self.manifest_path.parent / self.agent.system_prompt_file).resolve()
        if not prompt_path.exists():
            return ""
        return prompt_path.read_text(encoding="utf-8").strip()

    def to_dict(self, *, include_path: bool = False) -> dict[str, Any]:
        payload = {
            "slug": self.slug,
            "display_name": self.display_name,
            "status": self.status,
            "agent": self.agent.to_dict(),
            "runtime": self.runtime.to_dict(),
            "backend": self.backend.to_dict(),
        }
        if include_path:
            payload["manifest_path"] = str(self.manifest_path) if self.manifest_path else None
        return payload

    @classmethod
    def from_yaml_text(
        cls,
        text: str,
        *,
        manifest_path: Path | None = None,
    ) -> AgentManifest:
        raw = yaml.safe_load(text) or {}
        return cls.from_dict(raw, manifest_path=manifest_path)

    @classmethod
    def from_file(cls, path: Path) -> AgentManifest:
        return cls.from_yaml_text(path.read_text(encoding="utf-8"), manifest_path=path.resolve())

    @classmethod
    def from_dict(
        cls,
        raw: dict[str, Any],
        *,
        manifest_path: Path | None = None,
    ) -> AgentManifest:
        if not isinstance(raw, dict):
            raise ManifestValidationError(["manifest root must be an object"])

        normalized = _normalize_legacy_manifest(raw)
        errors: list[str] = []

        slug = _as_string(normalized.get("slug"), "slug", errors=errors)
        display_name = _as_string(normalized.get("display_name"), "display_name", errors=errors)
        status = _as_string(normalized.get("status", "active"), "status", errors=errors)
        if status and status.lower() not in {"active", "inactive"}:
            errors.append("status must be active or inactive")

        agent_raw = _as_dict(normalized.get("agent"), "agent", errors=errors)
        agent_working_dir = _as_string(
            agent_raw.get("working_dir", "/workspace"),
            "agent.working_dir",
            errors=errors,
        )
        agent_http_endpoint = _as_string(
            agent_raw.get("http_endpoint"),
            "agent.http_endpoint",
            errors=errors,
        )
        system_prompt_file = str(agent_raw.get("system_prompt_file") or "").strip() or None

        runtime_raw = _as_dict(normalized.get("runtime"), "runtime", errors=errors)
        runtime_driver = _as_string(
            runtime_raw.get("driver", "docker"), "runtime.driver", errors=errors
        )
        if runtime_driver and runtime_driver.lower() != "docker":
            errors.append("runtime.driver must be docker in v1")
        runtime_image = _as_string(runtime_raw.get("image"), "runtime.image", errors=errors)
        entrypoint = str(runtime_raw.get("entrypoint") or "").strip() or None
        command = _as_command(runtime_raw.get("command"), "runtime.command", errors=errors)

        mounts: list[RuntimeMount] = []
        mounts_raw = runtime_raw.get("mounts") or []
        if not isinstance(mounts_raw, list):
            errors.append("runtime.mounts must be a list")
            mounts_raw = []
        for index, item in enumerate(mounts_raw):
            mount_raw = _as_dict(item, f"runtime.mounts[{index}]", errors=errors)
            mount_type = _as_string(
                mount_raw.get("type", _detect_mount_type(mount_raw.get("source"))),
                f"runtime.mounts[{index}].type",
                errors=errors,
            ).lower()
            if mount_type not in {"bind", "volume"}:
                errors.append(f"runtime.mounts[{index}].type must be bind or volume")
            mount_mode = _as_string(
                mount_raw.get("mode", "rw"),
                f"runtime.mounts[{index}].mode",
                errors=errors,
            ).lower()
            if mount_mode not in {"rw", "ro"}:
                errors.append(f"runtime.mounts[{index}].mode must be rw or ro")
            mounts.append(
                RuntimeMount(
                    type=mount_type or "bind",
                    source=_as_string(
                        mount_raw.get("source"), f"runtime.mounts[{index}].source", errors=errors
                    ),
                    target=_as_string(
                        mount_raw.get("target"), f"runtime.mounts[{index}].target", errors=errors
                    ),
                    mode=mount_mode or "rw",
                )
            )

        env: dict[str, str] = {}
        env_raw = runtime_raw.get("env") or {}
        if not isinstance(env_raw, dict):
            errors.append("runtime.env must be an object")
        else:
            env = {
                str(key).strip(): str(value) for key, value in env_raw.items() if str(key).strip()
            }

        env_passthrough: list[str] = []
        env_passthrough_raw = runtime_raw.get("env_passthrough") or []
        if not isinstance(env_passthrough_raw, list):
            errors.append("runtime.env_passthrough must be a list")
        else:
            env_passthrough = [
                str(item).strip() for item in env_passthrough_raw if str(item).strip()
            ]

        backend_raw = _as_dict(normalized.get("backend"), "backend", errors=errors)
        backend_type = _as_string(backend_raw.get("type"), "backend.type", errors=errors)
        backend_config = backend_raw.get("config") or {}
        if not isinstance(backend_config, dict):
            errors.append("backend.config must be an object")
            backend_config = {}

        if errors:
            raise ManifestValidationError(errors)

        return cls(
            slug=slug,
            display_name=display_name,
            status=status.lower(),
            agent=AgentConfig(
                working_dir=agent_working_dir,
                http_endpoint=agent_http_endpoint,
                system_prompt_file=system_prompt_file,
            ),
            runtime=RuntimeConfig(
                driver=runtime_driver.lower(),
                image=runtime_image,
                entrypoint=entrypoint,
                command=command,
                mounts=mounts,
                env=env,
                env_passthrough=env_passthrough,
            ),
            backend=BackendConfig(
                type=backend_type,
                config=backend_config,
            ),
            manifest_path=manifest_path,
        )


def _normalize_legacy_manifest(raw: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(raw)
    agent = dict(normalized.get("agent") or {})
    runtime = dict(normalized.get("runtime") or {})
    backend = dict(normalized.get("backend") or {})

    if "working_dir" in normalized and "working_dir" not in agent:
        agent["working_dir"] = normalized.get("working_dir")
    if "http_endpoint" in normalized and "http_endpoint" not in agent:
        agent["http_endpoint"] = normalized.get("http_endpoint")
    if "system_prompt_file" in normalized and "system_prompt_file" not in agent:
        agent["system_prompt_file"] = normalized.get("system_prompt_file")

    if "backend_type" in normalized and "type" not in backend:
        backend["type"] = normalized.get("backend_type")

    legacy_container = normalized.get("container")
    if isinstance(legacy_container, dict):
        if "image" in legacy_container and "image" not in runtime:
            runtime["image"] = legacy_container.get("image")
        if "entrypoint" in legacy_container and "entrypoint" not in runtime:
            runtime["entrypoint"] = legacy_container.get("entrypoint")
        if "command" in legacy_container and "command" not in runtime:
            runtime["command"] = legacy_container.get("command")
        if "extra_env" in legacy_container and "env" not in runtime:
            runtime["env"] = legacy_container.get("extra_env")
        if "env_passthrough" in legacy_container and "env_passthrough" not in runtime:
            runtime["env_passthrough"] = legacy_container.get("env_passthrough")
        if "volumes" in legacy_container and "mounts" not in runtime:
            runtime["mounts"] = [
                {
                    "type": _detect_mount_type(item.get("source")),
                    "source": item.get("source"),
                    "target": item.get("target"),
                    "mode": "ro" if bool(item.get("read_only")) else "rw",
                }
                for item in legacy_container.get("volumes") or []
                if isinstance(item, dict)
            ]

    runtime.setdefault("driver", "docker")
    normalized["agent"] = agent
    normalized["runtime"] = runtime
    normalized["backend"] = backend
    return normalized
