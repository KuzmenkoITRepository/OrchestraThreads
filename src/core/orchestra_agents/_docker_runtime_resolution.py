"""Platform-derived runtime resolution for agent backends."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from core.orchestra_agents import _docker_runtime_specs as runtime_specs
from core.orchestra_agents import _docker_runtime_value_resolution as value_resolution
from core.orchestra_agents.manifest import AgentManifest, RuntimeMount


@dataclass(frozen=True)
class ResolvedRuntimeConfig:
    """Concrete runtime launch config after platform + manifest merging."""

    image: str
    command: tuple[str, ...]
    entrypoint: str | None
    env: Mapping[str, str]
    env_passthrough: tuple[str, ...]
    mounts: tuple[RuntimeMount, ...]


def _runtime_spec(
    manifest: AgentManifest,
) -> runtime_specs.BackendRuntimeSpec | None:
    return runtime_specs.BACKEND_RUNTIME_SPECS.get(manifest.backend.type)


def _resolve_runtime_image(
    manifest: AgentManifest,
    spec: runtime_specs.BackendRuntimeSpec | None,
) -> str:
    image = value_resolution.resolve_runtime_image(manifest, spec)
    if image:
        return image
    raise RuntimeError(
        f"agent {manifest.slug} is missing a runtime image for backend {manifest.backend.type!r}"
    )


def _resolve_runtime_mounts(
    manifest: AgentManifest,
) -> tuple[RuntimeMount, ...]:
    return tuple(manifest.runtime.mounts)


def resolve_backend_runtime(manifest: AgentManifest) -> ResolvedRuntimeConfig:
    """Resolve runtime launch config from backend defaults and manifest overrides."""

    spec = _runtime_spec(manifest)
    return ResolvedRuntimeConfig(
        image=_resolve_runtime_image(manifest, spec),
        command=value_resolution.resolve_runtime_command(manifest, spec),
        entrypoint=value_resolution.resolve_runtime_entrypoint(manifest, spec),
        env=value_resolution.resolve_runtime_env(manifest, spec),
        env_passthrough=value_resolution.resolve_runtime_env_passthrough(manifest, spec),
        mounts=_resolve_runtime_mounts(manifest),
    )
