"""Environment and mount rendering helpers for launch specs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from core.orchestra_agents.launch._field_health import resolve_http_endpoint
from core.orchestra_agents.launch._field_paths import (
    LaunchPathContext,
    resolve_bind_source_path,
    resolve_container_manifest_path,
)
from core.orchestra_agents.manifest import AgentManifest, RuntimeMount


@dataclass(frozen=True)
class RuntimeTemplateContext:
    """Runtime template values resolved from manifest + container state."""

    slug: str
    container_name: str
    backend_type: str
    working_dir: str

    def values(self) -> dict[str, str]:
        return {
            "slug": self.slug,
            "container_name": self.container_name,
            "backend_type": self.backend_type,
            "working_dir": self.working_dir,
        }


@dataclass(frozen=True)
class RenderedMount:
    """Resolved runtime mount values."""

    mount_type: str
    source: str
    target: str
    mode: str


def runtime_template_context(
    manifest: AgentManifest, *, container_name: str
) -> RuntimeTemplateContext:
    """Build shared runtime template context for env and mount rendering."""

    return RuntimeTemplateContext(
        slug=manifest.slug,
        container_name=container_name,
        backend_type=manifest.backend.type,
        working_dir=manifest.agent.working_dir,
    )


def resolve_agent_environment(
    manifest: AgentManifest,
    *,
    container_name: str,
    path_context: LaunchPathContext,
) -> dict[str, str]:
    """Return base orchestra-managed environment entries."""

    environment = {
        "ORCHESTRA_AGENT_SLUG": manifest.slug,
        "ORCHESTRA_AGENT_BACKEND_TYPE": manifest.backend.type,
        "ORCHESTRA_AGENT_HTTP_ENDPOINT": resolve_http_endpoint(
            manifest,
            container_name=container_name,
        ),
        "ORCHESTRA_AGENT_WORKING_DIR": manifest.agent.working_dir,
        "ORCHESTRA_AGENT_ALLOWED_PEER_AGENT_SLUGS": ",".join(
            manifest.agent.allowed_peer_agent_slugs
        ),
        "ORCHESTRA_AGENT_MANIFESTS_DIR": path_context.manifest_mount_path,
        "ORCHESTRA_AGENT_MANIFEST": resolve_container_manifest_path(
            manifest,
            path_context=path_context,
        ),
    }
    if manifest.agent.system_prompt_file:
        environment["ORCHESTRA_AGENT_SYSTEM_PROMPT_FILE"] = manifest.agent.system_prompt_file
    return environment


def render_runtime_environment(
    *,
    context: RuntimeTemplateContext,
    env: Mapping[str, str],
) -> dict[str, str]:
    """Render runtime env templates."""

    values = context.values()
    rendered: dict[str, str] = {}
    for key, value in env.items():
        rendered[key] = _format_template(
            str(value),
            values,
            field_name=f"runtime.env[{key!r}]",
            slug=context.slug,
        )
    return rendered


def render_mount(
    *,
    manifest: AgentManifest,
    mount: RuntimeMount,
    mount_index: int,
    context: RuntimeTemplateContext,
    path_context: LaunchPathContext,
) -> RenderedMount:
    """Render mount source, target, and mode for a runtime mount."""

    values = context.values()
    source_template = _format_template(
        mount.source,
        values,
        field_name=f"runtime.mounts[{mount_index}].source",
        slug=context.slug,
    )
    target = _format_template(
        mount.target,
        values,
        field_name=f"runtime.mounts[{mount_index}].target",
        slug=context.slug,
    )
    source = source_template
    if mount.type == "bind":
        source = str(
            resolve_bind_source_path(
                manifest,
                source_template,
                path_context=path_context,
            )
        )
    return RenderedMount(mount_type=mount.type, source=source, target=target, mode=mount.mode)


def _format_template(
    template: str,
    values: Mapping[str, str],
    *,
    field_name: str,
    slug: str,
) -> str:
    try:
        return str(template).format(**values)
    except KeyError as error:
        raise RuntimeError(
            f"invalid {field_name} template for {slug}: missing {error.args[0]!r}"
        ) from error
    except ValueError as error:
        raise RuntimeError(f"invalid {field_name} template for {slug}") from error
