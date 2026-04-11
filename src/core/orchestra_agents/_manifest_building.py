"""Helpers for building public manifest objects from parsed payloads."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.orchestra_agents._manifest_parsing import ParsedManifest

if TYPE_CHECKING:
    from core.orchestra_agents.manifest import (
        AgentConfig,
        AgentManifest,
        BackendConfig,
        RuntimeConfig,
        RuntimeMount,
    )


def build_manifest(parsed: ParsedManifest) -> AgentManifest:
    """Build a public manifest object from parsed manifest data."""
    from core.orchestra_agents.manifest import AgentManifest

    return AgentManifest(
        slug=parsed.slug,
        display_name=parsed.display_name,
        status=parsed.status,
        agent=_build_agent_config(parsed.agent),
        runtime=_build_runtime_config(parsed.runtime),
        backend=_build_backend_config(parsed.backend),
        manifest_path=parsed.manifest_path,
        auto_start=parsed.auto_start,
    )


def _build_agent_config(agent_payload: dict[str, Any]) -> AgentConfig:
    from core.orchestra_agents.manifest import AgentConfig

    return AgentConfig(
        working_dir=str(agent_payload["working_dir"]),
        http_endpoint=str(agent_payload["http_endpoint"]),
        system_prompt_file=agent_payload["system_prompt_file"],
        allowed_peer_agent_slugs=list(agent_payload["allowed_peer_agent_slugs"]),
    )


def _build_runtime_config(runtime_payload: dict[str, Any]) -> RuntimeConfig:
    from core.orchestra_agents.manifest import RuntimeConfig

    return RuntimeConfig(
        driver=str(runtime_payload["driver"]),
        image=str(runtime_payload["image"]),
        entrypoint=runtime_payload["entrypoint"],
        command=list(runtime_payload["command"]),
        mounts=_build_runtime_mounts(runtime_payload["mounts"]),
        env=dict(runtime_payload["env"]),
        env_passthrough=list(runtime_payload["env_passthrough"]),
    )


def _build_runtime_mounts(mounts_payload: list[dict[str, str]]) -> list[RuntimeMount]:
    return [_build_runtime_mount(mount_payload) for mount_payload in mounts_payload]


def _build_runtime_mount(mount_payload: dict[str, str]) -> RuntimeMount:
    from core.orchestra_agents.manifest import RuntimeMount

    return RuntimeMount(**mount_payload)


def _build_backend_config(backend_payload: dict[str, Any]) -> BackendConfig:
    from core.orchestra_agents.manifest import BackendConfig

    return BackendConfig(
        type=str(backend_payload["type"]),
        config=dict(backend_payload["config"]),
    )
