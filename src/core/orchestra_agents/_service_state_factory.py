"""Factory collaborators for orchestra agents service state."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Protocol, cast

from core.orchestra_agents.launch import (
    compose_runtime,
    docker_cli_runtime,
    launch_spec,
    runtime_protocol,
)
from core.orchestra_agents.launch import spec_builder as launch_spec_builder
from core.orchestra_agents.registry import AgentManifestRegistry

RuntimeSelector = Callable[
    [launch_spec.LaunchSpec, str, runtime_protocol.ContainerRuntime],
    runtime_protocol.ContainerRuntime,
]


class _RuntimeConfig(Protocol):
    host_manifests_root: Path | None
    container_name_prefix: str
    default_network: str | None
    manifest_mount_path: str
    health_timeout_seconds: float
    auto_build_local_images: bool
    build_context_root: Path
    compose_runtime_dir: Path
    compose_project_name: str
    runtime_name: str | None


class _RuntimeConfigClass(Protocol):
    @classmethod
    def from_manifests_root(cls, manifests_root: Path) -> _RuntimeConfig: ...


@dataclass(frozen=True)
class ServiceStateParts:
    registry: AgentManifestRegistry
    builder: launch_spec_builder.LaunchSpecBuilder
    default_runtime: runtime_protocol.ContainerRuntime
    runtime_selector: RuntimeSelector | None


@dataclass(frozen=True)
class _FactoryDeps:
    registry: AgentManifestRegistry | None
    builder: launch_spec_builder.LaunchSpecBuilder | None
    default_runtime: runtime_protocol.ContainerRuntime | None
    runtime_selector: RuntimeSelector | None
    docker_cli_runtime: runtime_protocol.ContainerRuntime | None


class ServiceStateFactory:
    @classmethod
    def create(
        cls,
        *,
        manifests_root: str | None,
        deps: object,
    ) -> ServiceStateParts:
        resolved_deps = cls._coerce_deps(deps)
        registry = cls._resolve_registry(manifests_root=manifests_root, deps=resolved_deps)
        env_config = cls._runtime_config_class().from_manifests_root(
            Path(registry.manifests_root).expanduser().resolve()
        )
        return ServiceStateParts(
            registry=registry,
            builder=cls._resolve_builder(
                registry=registry, env_config=env_config, deps=resolved_deps
            ),
            default_runtime=cls._resolve_default_runtime(env_config=env_config, deps=resolved_deps),
            runtime_selector=cls._resolve_runtime_selector(
                env_config=env_config, deps=resolved_deps
            ),
        )

    @staticmethod
    def _resolve_registry(
        *,
        manifests_root: str | None,
        deps: _FactoryDeps,
    ) -> AgentManifestRegistry:
        if deps.registry is not None:
            return deps.registry
        return AgentManifestRegistry(manifests_root=manifests_root)

    @staticmethod
    def _resolve_builder(
        *,
        registry: AgentManifestRegistry,
        env_config: _RuntimeConfig,
        deps: _FactoryDeps,
    ) -> launch_spec_builder.LaunchSpecBuilder:
        if deps.builder is not None:
            return deps.builder
        manifests_root = Path(registry.manifests_root).expanduser().resolve()
        return launch_spec_builder.LaunchSpecBuilder(
            manifests_root=manifests_root,
            host_manifests_root=env_config.host_manifests_root,
            container_name_prefix=env_config.container_name_prefix,
            default_network=env_config.default_network,
            manifest_mount_path=env_config.manifest_mount_path,
            compose_runtime_dir=env_config.compose_runtime_dir,
        )

    @staticmethod
    def _resolve_default_runtime(
        *,
        env_config: _RuntimeConfig,
        deps: _FactoryDeps,
    ) -> runtime_protocol.ContainerRuntime:
        if deps.default_runtime is not None:
            return deps.default_runtime
        return compose_runtime.ComposeRuntime(
            compose_project_name=env_config.compose_project_name,
            health_timeout_seconds=env_config.health_timeout_seconds,
            auto_build_local_images=env_config.auto_build_local_images,
            build_context_root=env_config.build_context_root,
        )

    @staticmethod
    def _resolve_runtime_selector(
        *,
        env_config: _RuntimeConfig,
        deps: _FactoryDeps,
    ) -> RuntimeSelector | None:
        if deps.runtime_selector is not None:
            return deps.runtime_selector
        runtime_name = env_config.runtime_name
        if runtime_name is None:
            return None
        if runtime_name == "compose":
            return _FixedRuntimeSelector(runtime=None)
        if runtime_name != "docker-cli":
            raise ValueError(f"unsupported ORCHESTRA_AGENTS_RUNTIME: {runtime_name!r}")
        return _FixedRuntimeSelector(
            runtime=deps.docker_cli_runtime
            or docker_cli_runtime.DockerCliRuntime(
                health_timeout_seconds=env_config.health_timeout_seconds,
                auto_build_local_images=env_config.auto_build_local_images,
                build_context_root=env_config.build_context_root,
            ),
        )

    @staticmethod
    def _coerce_deps(deps: object) -> _FactoryDeps:
        return _FactoryDeps(
            registry=getattr(deps, "registry", None),
            builder=getattr(deps, "builder", None),
            default_runtime=getattr(deps, "default_runtime", None),
            runtime_selector=getattr(deps, "runtime_selector", None),
            docker_cli_runtime=getattr(deps, "docker_cli_runtime", None),
        )

    @staticmethod
    def _runtime_config_class() -> _RuntimeConfigClass:
        return cast(
            _RuntimeConfigClass,
            import_module("core.orchestra_agents._service_runtime_config").ServiceRuntimeConfig,
        )


@dataclass(frozen=True)
class _FixedRuntimeSelector:
    runtime: runtime_protocol.ContainerRuntime | None

    def __call__(
        self,
        _spec: launch_spec.LaunchSpec,
        _operation: str,
        current_default: runtime_protocol.ContainerRuntime,
    ) -> runtime_protocol.ContainerRuntime:
        if self.runtime is None:
            return current_default
        return self.runtime
