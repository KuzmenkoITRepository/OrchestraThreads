"""Helper functions for backend runtime value resolution."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType

from core.orchestra_agents import _docker_runtime_specs as runtime_specs
from core.orchestra_agents.manifest import AgentManifest


class _RuntimeSpecValues:
    @staticmethod
    def image(spec: runtime_specs.BackendRuntimeSpec | None) -> str:
        if spec is None:
            return ""
        return spec.image

    @staticmethod
    def command(spec: runtime_specs.BackendRuntimeSpec | None) -> tuple[str, ...]:
        if spec is None:
            return ()
        return spec.command

    @staticmethod
    def entrypoint(spec: runtime_specs.BackendRuntimeSpec | None) -> str | None:
        if spec is None:
            return None
        return spec.entrypoint

    @staticmethod
    def env(spec: runtime_specs.BackendRuntimeSpec | None) -> dict[str, str]:
        if spec is None:
            return {}
        return dict(spec.env)

    @staticmethod
    def env_passthrough(spec: runtime_specs.BackendRuntimeSpec | None) -> Sequence[str]:
        if spec is None:
            return ()
        return spec.env_passthrough

    @staticmethod
    def merge_unique_keys(defaults: Sequence[str], overrides: Sequence[str]) -> tuple[str, ...]:
        merged_keys = list(defaults)
        for key in overrides:
            if key not in merged_keys:
                merged_keys.append(key)
        return tuple(merged_keys)


def resolve_runtime_image(
    manifest: AgentManifest,
    spec: runtime_specs.BackendRuntimeSpec | None,
) -> str:
    """Resolve runtime image using manifest override first."""

    configured_image = str(manifest.runtime.image).strip()
    if configured_image:
        return configured_image
    return _RuntimeSpecValues.image(spec)


def resolve_runtime_command(
    manifest: AgentManifest,
    spec: runtime_specs.BackendRuntimeSpec | None,
) -> tuple[str, ...]:
    """Resolve runtime command using manifest override first."""

    configured_command = tuple(manifest.runtime.command)
    if configured_command:
        return configured_command
    return _RuntimeSpecValues.command(spec)


def resolve_runtime_entrypoint(
    manifest: AgentManifest,
    spec: runtime_specs.BackendRuntimeSpec | None,
) -> str | None:
    """Resolve runtime entrypoint using manifest override first."""

    if manifest.runtime.entrypoint:
        return manifest.runtime.entrypoint
    return _RuntimeSpecValues.entrypoint(spec)


def resolve_runtime_env(
    manifest: AgentManifest,
    spec: runtime_specs.BackendRuntimeSpec | None,
) -> Mapping[str, str]:
    """Merge default and manifest runtime env."""

    default_env = _RuntimeSpecValues.env(spec)
    default_env.update(manifest.runtime.env)
    return MappingProxyType(default_env)


def resolve_runtime_env_passthrough(
    manifest: AgentManifest,
    spec: runtime_specs.BackendRuntimeSpec | None,
) -> tuple[str, ...]:
    """Merge default and manifest env passthrough keys."""

    return _RuntimeSpecValues.merge_unique_keys(
        _RuntimeSpecValues.env_passthrough(spec),
        manifest.runtime.env_passthrough,
    )
