from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from core.orchestra_agents.docker_driver import DockerDriver
from core.orchestra_agents.errors import ServiceError
from core.orchestra_agents.manifest import AgentManifest
from core.orchestra_agents.registry import AgentManifestRegistry


@dataclass(frozen=True)
class ServiceState:
    registry: AgentManifestRegistry
    driver: DockerDriver
    manifest_class: type[AgentManifest]
    lock: asyncio.Lock

    @classmethod
    def create(
        cls,
        *,
        manifests_root: str | None = None,
        registry: Any = None,
        driver: Any = None,
    ) -> ServiceState:
        resolved_registry = registry or AgentManifestRegistry(manifests_root=manifests_root)
        resolved_driver = driver or DockerDriver(manifests_root=resolved_registry.manifests_root)
        return cls(
            registry=resolved_registry,
            driver=resolved_driver,
            manifest_class=AgentManifest,
            lock=asyncio.Lock(),
        )

    def require_manifest(self, slug: str) -> AgentManifest:
        normalized = str(slug or "").strip()
        if not normalized:
            raise ServiceError(400, "slug is required")
        try:
            return self.registry.require(normalized)
        except KeyError as exc:
            raise ServiceError(404, str(exc)) from exc
