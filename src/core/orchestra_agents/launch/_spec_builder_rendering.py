"""Private rendering helpers for launch spec builder."""

from __future__ import annotations

import os

from core.orchestra_agents.launch._builder_config import BuilderPaths
from core.orchestra_agents.launch._resolved_runtime_profile import ResolvedRuntimeProfile
from core.orchestra_agents.launch._spec_field_resolution import (
    LaunchPathContext,
    RenderedMount,
    render_mount,
    render_runtime_environment,
    resolve_agent_environment,
    resolve_bind_source_path,
    runtime_template_context,
)
from core.orchestra_agents.launch.launch_spec import ResolvedMount
from core.orchestra_agents.manifest import AgentManifest


def build_environment(
    manifest: AgentManifest,
    resolved_runtime: ResolvedRuntimeProfile,
    *,
    container_name: str,
    builder_paths: BuilderPaths,
) -> dict[str, str]:
    """Build launch environment from manifest and runtime profile."""

    template_context = runtime_template_context(
        manifest,
        container_name=container_name,
    )
    environment = resolve_agent_environment(
        manifest,
        container_name=container_name,
        path_context=_path_context(builder_paths),
    )
    environment.update(
        render_runtime_environment(
            context=template_context,
            env=resolved_runtime.env,
        )
    )
    environment.update(
        _resolve_env_passthrough(
            env_passthrough=resolved_runtime.env_passthrough,
            host_env=os.environ,
        )
    )
    return environment


def build_mounts(
    manifest: AgentManifest,
    *,
    container_name: str,
    builder_paths: BuilderPaths,
) -> tuple[ResolvedMount, ...]:
    """Build launch mounts from manifest mount templates."""

    template_context = runtime_template_context(
        manifest,
        container_name=container_name,
    )
    path_context = _path_context(builder_paths)
    mounts = [_manifest_root_mount(builder_paths)]
    for mount_index, mount in enumerate(manifest.runtime.mounts):
        mounts.append(
            _resolved_mount(
                _validated_rendered_mount(
                    manifest,
                    render_mount(
                        manifest=manifest,
                        mount=mount,
                        mount_index=mount_index,
                        context=template_context,
                        path_context=path_context,
                    ),
                    path_context=path_context,
                )
            )
        )
    return tuple(mounts)


def _path_context(builder_paths: BuilderPaths) -> LaunchPathContext:
    return LaunchPathContext(
        manifests_root=builder_paths.manifests_root,
        host_manifests_root=builder_paths.host_manifests_root,
        manifest_mount_path=builder_paths.manifest_mount_path,
    )


def _manifest_root_mount(builder_paths: BuilderPaths) -> ResolvedMount:
    return ResolvedMount(
        type="bind",
        source=str(builder_paths.host_manifests_root),
        target=builder_paths.manifest_mount_path,
        mode="ro",
    )


def _resolved_mount(rendered_mount: RenderedMount) -> ResolvedMount:
    return ResolvedMount(
        type=rendered_mount.mount_type,
        source=rendered_mount.source,
        target=rendered_mount.target,
        mode=rendered_mount.mode,
    )


def _resolve_env_passthrough(
    *,
    env_passthrough: tuple[str, ...],
    host_env: os._Environ[str],
) -> dict[str, str]:
    rendered: dict[str, str] = {}
    for key in env_passthrough:
        host_value = host_env.get(key)
        if host_value is not None and host_value != "":
            rendered[key] = host_value
    return rendered


def _validated_rendered_mount(
    manifest: AgentManifest,
    rendered_mount: RenderedMount,
    *,
    path_context: LaunchPathContext,
) -> RenderedMount:
    if rendered_mount.mount_type != "bind":
        return rendered_mount
    source_path = resolve_bind_source_path(
        manifest,
        rendered_mount.source,
        path_context=path_context,
    )
    if not source_path.exists():
        raise RuntimeError(f"bind mount source does not exist: {source_path}")
    return RenderedMount(
        mount_type=rendered_mount.mount_type,
        source=str(source_path),
        target=rendered_mount.target,
        mode=rendered_mount.mode,
    )
