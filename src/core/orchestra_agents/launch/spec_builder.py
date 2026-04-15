"""Pure launch spec builder for orchestra agents."""

from __future__ import annotations

from typing import Unpack

from core.orchestra_agents.launch._builder_config import (
    BuilderInitKwargs as _BuilderInitKwargs,
)
from core.orchestra_agents.launch._builder_config import BuilderPaths as _BuilderPaths
from core.orchestra_agents.launch._builder_config import (
    resolve_builder_config as _resolve_builder_config,
)
from core.orchestra_agents.launch._resolved_runtime_profile import (
    ResolvedRuntimeProfile as ResolvedRuntimeProfile,
)
from core.orchestra_agents.launch._runtime_profile_resolution import (
    resolve_runtime_profile as _resolve_runtime_profile_impl,
)
from core.orchestra_agents.launch._spec_builder_rendering import (
    build_environment as _build_environment,
)
from core.orchestra_agents.launch._spec_builder_rendering import build_mounts as _build_mounts
from core.orchestra_agents.launch._spec_field_resolution import (
    resolve_compose_file_path,
    resolve_compose_service_name,
    resolve_container_name,
    resolve_healthcheck_command,
)
from core.orchestra_agents.launch.launch_spec import LaunchSpec, ResolvedHealthcheck
from core.orchestra_agents.manifest import AgentManifest


class LaunchSpecBuilder:
    """Build pure launch specs from manifests and backend defaults."""

    def __init__(
        self,
        *,
        paths: _BuilderPaths | None = None,
        **kwargs: Unpack[_BuilderInitKwargs],
    ) -> None:
        self._config = _resolve_builder_config(paths=paths, **kwargs)

    def build(self, manifest: AgentManifest) -> LaunchSpec:
        """Build launch spec from manifest defaults and runtime overrides."""

        container_name = resolve_container_name(
            slug=manifest.slug,
            prefix=self._config.container_name_prefix,
        )
        resolved_runtime = self._resolve_runtime_profile(manifest)
        return LaunchSpec(
            slug=manifest.slug,
            container_name=container_name,
            image=resolved_runtime.image,
            labels=(
                ("orchestra.agent_slug", manifest.slug),
                ("orchestra.backend_type", manifest.backend.type),
            ),
            env=tuple(
                _build_environment(
                    manifest,
                    resolved_runtime,
                    container_name=container_name,
                    builder_paths=self._config.paths,
                ).items()
            ),
            mounts=_build_mounts(
                manifest,
                container_name=container_name,
                builder_paths=self._config.paths,
            ),
            command=resolved_runtime.command,
            entrypoint=resolved_runtime.entrypoint,
            working_dir=manifest.agent.working_dir,
            default_network=self._config.default_network,
            healthcheck=ResolvedHealthcheck(
                test=(
                    "CMD-SHELL",
                    resolve_healthcheck_command(
                        manifest,
                        container_name=container_name,
                    ),
                ),
            ),
            compose_file_path=resolve_compose_file_path(
                self._config.paths.compose_runtime_dir,
                slug=manifest.slug,
            ),
            compose_service_name=resolve_compose_service_name(manifest.slug),
        )

    def runtime_profile(self, manifest: AgentManifest) -> ResolvedRuntimeProfile:
        """Expose merged runtime profile including build metadata."""

        return self._resolve_runtime_profile(manifest)

    def _resolve_runtime_profile(self, manifest: AgentManifest) -> ResolvedRuntimeProfile:
        return _resolve_runtime_profile_impl(manifest, self._config.paths)
