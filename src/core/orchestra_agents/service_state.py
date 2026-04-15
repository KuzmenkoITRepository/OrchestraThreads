from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module
from typing import Any, cast

from core.orchestra_agents.errors import ServiceError
from core.orchestra_agents.launch import launch_spec, runtime_protocol
from core.orchestra_agents.launch import spec_builder as launch_spec_builder
from core.orchestra_agents.manifest import AgentManifest
from core.orchestra_agents.registry import AgentManifestRegistry

RuntimeSelector = Callable[
    [launch_spec.LaunchSpec, str, runtime_protocol.ContainerRuntime],
    runtime_protocol.ContainerRuntime,
]


@dataclass(frozen=True)
class ServiceStateDeps:
    registry: AgentManifestRegistry | None = None
    builder: launch_spec_builder.LaunchSpecBuilder | None = None
    default_runtime: runtime_protocol.ContainerRuntime | None = None
    runtime_selector: RuntimeSelector | None = None
    docker_cli_runtime: runtime_protocol.ContainerRuntime | None = None


def _normalize_slug(slug: str) -> str:
    normalized = str(slug or "").strip()
    if not normalized:
        raise ServiceError(400, "slug is required")
    return normalized


class _DriverCompatibilityAdapter:
    def __init__(self, state: ServiceState) -> None:
        self._state = state

    def container_name(self, slug: str) -> str:
        manifest = self._state.require_manifest(slug)
        spec = self._state.build_spec(manifest)
        runtime = self._state.resolve_runtime(spec, operation="container_name")
        return runtime.container_name(spec)

    def status(self, manifest: AgentManifest) -> dict[str, Any]:
        spec = self._state.build_spec(manifest)
        runtime = self._state.resolve_runtime(spec, operation="status")
        return _payload_dict(runtime.status(spec))

    def start(self, manifest: AgentManifest) -> dict[str, Any]:
        spec = self._state.build_spec(manifest)
        runtime = self._state.resolve_runtime(spec, operation="start")
        return _payload_dict(runtime.start(spec))

    def stop(self, slug: str, *, remove: bool = False) -> dict[str, Any]:
        manifest = self._state.require_manifest(slug)
        spec = self._state.build_spec(manifest)
        runtime = self._state.resolve_runtime(spec, operation="stop")
        return _payload_dict(runtime.stop(spec, remove=remove))

    def restart(self, manifest: AgentManifest) -> dict[str, Any]:
        spec = self._state.build_spec(manifest)
        runtime = self._state.resolve_runtime(spec, operation="restart")
        return _payload_dict(runtime.restart(spec))


def _payload_dict(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return dict(payload)
    return cast(dict[str, Any], payload.to_dict())


@dataclass(frozen=True)
class ServiceState:
    registry: AgentManifestRegistry
    builder: launch_spec_builder.LaunchSpecBuilder
    default_runtime: runtime_protocol.ContainerRuntime
    runtime_selector: RuntimeSelector | None
    manifest_class: type[AgentManifest]
    lock: asyncio.Lock

    @classmethod
    def create(
        cls,
        *,
        manifests_root: str | None = None,
        deps: ServiceStateDeps | None = None,
    ) -> ServiceState:
        state_factory = cast(
            type[Any],
            import_module("core.orchestra_agents._service_state_factory").ServiceStateFactory,
        )
        resolved_deps = deps or ServiceStateDeps()
        resolved_parts = state_factory.create(
            manifests_root=manifests_root,
            deps=resolved_deps,
        )
        return cls(
            registry=resolved_parts.registry,
            builder=resolved_parts.builder,
            default_runtime=resolved_parts.default_runtime,
            runtime_selector=resolved_parts.runtime_selector,
            manifest_class=AgentManifest,
            lock=asyncio.Lock(),
        )

    def require_manifest(self, slug: str) -> AgentManifest:
        normalized = _normalize_slug(slug)
        try:
            return self.registry.require(normalized)
        except KeyError as exc:
            raise ServiceError(404, str(exc)) from exc

    def build_spec(self, manifest: AgentManifest) -> launch_spec.LaunchSpec:
        return self.builder.build(manifest)

    def resolve_runtime(
        self,
        spec: launch_spec.LaunchSpec,
        *,
        operation: str,
    ) -> runtime_protocol.ContainerRuntime:
        if self.runtime_selector is None:
            return self.default_runtime
        return self.runtime_selector(spec, operation, self.default_runtime)

    @property
    def driver(self) -> _DriverCompatibilityAdapter:
        return _DriverCompatibilityAdapter(self)
