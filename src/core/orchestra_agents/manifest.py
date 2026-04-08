"""Manifest schema for orchestra_agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from core.orchestra_agents._manifest_parsing import _ManifestParser

RuntimePayload = dict[str, Any]


@dataclass(frozen=True)
class AgentConfig:
    """Logical agent contract fields."""

    working_dir: str
    http_endpoint: str
    system_prompt_file: str | None = None
    allowed_peer_agent_slugs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "working_dir": self.working_dir,
            "http_endpoint": self.http_endpoint,
            "system_prompt_file": self.system_prompt_file,
            "allowed_peer_agent_slugs": list(self.allowed_peer_agent_slugs),
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
        payload: dict[str, Any] = {
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
        parsed = _ManifestParser(raw, manifest_path=manifest_path).parse()

        return cls(
            slug=parsed.slug,
            display_name=parsed.display_name,
            status=parsed.status,
            agent=AgentConfig(
                working_dir=str(parsed.agent["working_dir"]),
                http_endpoint=str(parsed.agent["http_endpoint"]),
                system_prompt_file=parsed.agent["system_prompt_file"],
                allowed_peer_agent_slugs=list(parsed.agent["allowed_peer_agent_slugs"]),
            ),
            runtime=RuntimeConfig(
                driver=str(parsed.runtime["driver"]),
                image=str(parsed.runtime["image"]),
                entrypoint=parsed.runtime["entrypoint"],
                command=list(parsed.runtime["command"]),
                mounts=[RuntimeMount(**mount) for mount in parsed.runtime["mounts"]],
                env=dict(parsed.runtime["env"]),
                env_passthrough=list(parsed.runtime["env_passthrough"]),
            ),
            backend=BackendConfig(
                type=str(parsed.backend["type"]),
                config=dict(parsed.backend["config"]),
            ),
            manifest_path=parsed.manifest_path,
        )
