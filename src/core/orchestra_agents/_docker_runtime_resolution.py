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


def resolve_backend_runtime(manifest: AgentManifest) -> ResolvedRuntimeConfig:
    """Resolve runtime launch config from backend defaults and manifest overrides."""

    spec = runtime_specs.BACKEND_RUNTIME_SPECS.get(manifest.backend.type)
    image = value_resolution.resolve_runtime_image(manifest, spec)
    if not image:
        raise RuntimeError(
            f"agent {manifest.slug} is missing a runtime image for backend {manifest.backend.type!r}"
        )
    return ResolvedRuntimeConfig(
        image=image,
        command=value_resolution.resolve_runtime_command(manifest, spec),
        entrypoint=value_resolution.resolve_runtime_entrypoint(manifest, spec),
        env=value_resolution.resolve_runtime_env(manifest, spec),
        env_passthrough=value_resolution.resolve_runtime_env_passthrough(manifest, spec),
        mounts=tuple(manifest.runtime.mounts),
    )
