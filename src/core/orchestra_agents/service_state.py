from __future__ import annotations

import asyncio
from dataclasses import dataclass

from core.orchestra_agents.docker_driver.driver import DockerDriver
from core.orchestra_agents.errors import ServiceError
from core.orchestra_agents.manifest import AgentManifest
from core.orchestra_agents.registry import AgentManifestRegistry


def _resolve_registry(
    *,
    manifests_root: str | None,
    registry: AgentManifestRegistry | None,
) -> AgentManifestRegistry:
    if registry is not None:
        return registry
    return AgentManifestRegistry(manifests_root=manifests_root)


def _resolve_driver(
    *,
    registry: AgentManifestRegistry,
    driver: DockerDriver | None,
) -> DockerDriver:
    if driver is not None:
        return driver
    return DockerDriver(manifests_root=registry.manifests_root)


def _normalize_slug(slug: str) -> str:
    normalized = str(slug or "").strip()
    if not normalized:
        raise ServiceError(400, "slug is required")
    return normalized


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
        registry: AgentManifestRegistry | None = None,
        driver: DockerDriver | None = None,
    ) -> ServiceState:
        resolved_registry = _resolve_registry(
            manifests_root=manifests_root,
            registry=registry,
        )
        resolved_driver = _resolve_driver(
            registry=resolved_registry,
            driver=driver,
        )
        return cls(
            registry=resolved_registry,
            driver=resolved_driver,
            manifest_class=AgentManifest,
            lock=asyncio.Lock(),
        )

    def require_manifest(self, slug: str) -> AgentManifest:
        normalized = _normalize_slug(slug)
        try:
            return self.registry.require(normalized)
        except KeyError as exc:
            raise ServiceError(404, str(exc)) from exc
