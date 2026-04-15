"""Runtime profile resolution helpers for launch spec builder."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from core.orchestra_agents.launch import backend_profiles
from core.orchestra_agents.launch._builder_config import BuilderPaths
from core.orchestra_agents.launch._resolved_runtime_profile import ResolvedRuntimeProfile
from core.orchestra_agents.manifest import AgentManifest


def resolve_runtime_profile(
    manifest: AgentManifest,
    _builder_paths: BuilderPaths,
) -> ResolvedRuntimeProfile:
    """Resolve runtime profile from backend defaults and manifest overrides."""

    profile = backend_profiles.backend_profile(manifest.backend.type)
    image = str(manifest.runtime.image).strip() or _profile_image(profile)
    command = tuple(manifest.runtime.command) or _profile_command(profile)
    entrypoint = manifest.runtime.entrypoint or _profile_entrypoint(profile)
    if not image:
        raise RuntimeError(
            f"agent {manifest.slug} is missing a runtime image for backend {manifest.backend.type!r}"
        )
    if not command:
        raise RuntimeError(
            f"agent {manifest.slug} is missing a runtime command for backend {manifest.backend.type!r}"
        )
    profile_env = dict(_profile_env(profile))
    profile_env.update(manifest.runtime.env)
    return ResolvedRuntimeProfile(
        image=image,
        command=command,
        entrypoint=entrypoint,
        env=profile_env,
        env_passthrough=backend_profiles.merge_env_passthrough(
            _profile_env_passthrough(profile),
            manifest.runtime.env_passthrough,
        ),
        build_dockerfile=_profile_build_dockerfile(profile),
    )


def _profile_image(profile: backend_profiles.BackendProfile | None) -> str:
    if profile is None:
        return ""
    return profile.image


def _profile_command(profile: backend_profiles.BackendProfile | None) -> tuple[str, ...]:
    if profile is None:
        return ()
    return profile.command


def _profile_entrypoint(profile: backend_profiles.BackendProfile | None) -> str | None:
    if profile is None:
        return None
    return profile.entrypoint


def _profile_env(profile: backend_profiles.BackendProfile | None) -> Mapping[str, str]:
    if profile is None:
        return {}
    return profile.env


def _profile_env_passthrough(
    profile: backend_profiles.BackendProfile | None,
) -> Sequence[str]:
    if profile is None:
        return ()
    return profile.env_passthrough


def _profile_build_dockerfile(profile: backend_profiles.BackendProfile | None) -> str | None:
    if profile is None:
        return None
    return profile.build_dockerfile
