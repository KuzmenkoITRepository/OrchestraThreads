"""Helper functions for backend runtime value resolution."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType

from core.orchestra_agents import _docker_runtime_specs as runtime_specs
from core.orchestra_agents.manifest import AgentManifest


def resolve_runtime_image(
    manifest: AgentManifest,
    spec: runtime_specs.BackendRuntimeSpec | None,
) -> str:
    """Resolve runtime image using manifest override first."""

    configured_image = str(manifest.runtime.image).strip()
    if configured_image:
        return configured_image
    if spec is None:
        return ""
    return spec.image


def resolve_runtime_command(
    manifest: AgentManifest,
    spec: runtime_specs.BackendRuntimeSpec | None,
) -> tuple[str, ...]:
    """Resolve runtime command using manifest override first."""

    configured_command = tuple(manifest.runtime.command)
    if configured_command:
        return configured_command
    if spec is None:
        return ()
    return spec.command


def resolve_runtime_entrypoint(
    manifest: AgentManifest,
    spec: runtime_specs.BackendRuntimeSpec | None,
) -> str | None:
    """Resolve runtime entrypoint using manifest override first."""

    if manifest.runtime.entrypoint:
        return manifest.runtime.entrypoint
    if spec is None:
        return None
    return spec.entrypoint


def resolve_runtime_env(
    manifest: AgentManifest,
    spec: runtime_specs.BackendRuntimeSpec | None,
) -> Mapping[str, str]:
    """Merge default and manifest runtime env."""

    default_env = {} if spec is None else dict(spec.env)
    default_env.update(manifest.runtime.env)
    return MappingProxyType(default_env)


def resolve_runtime_env_passthrough(
    manifest: AgentManifest,
    spec: runtime_specs.BackendRuntimeSpec | None,
) -> tuple[str, ...]:
    """Merge default and manifest env passthrough keys."""

    defaults: Sequence[str] = () if spec is None else spec.env_passthrough
    merged_keys = list(defaults)
    for key in manifest.runtime.env_passthrough:
        if key not in merged_keys:
            merged_keys.append(key)
    return tuple(merged_keys)
