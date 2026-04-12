from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.orchestra_agents.manifest import AgentManifest
    from core.orchestra_agents.service_state import ServiceState


def _agent_payload(
    manifest: AgentManifest,
    *,
    runtime: dict[str, Any],
    state: ServiceState,
) -> dict[str, Any]:
    running = bool(runtime.get("running"))
    healthy = bool(runtime.get("healthy"))
    metadata: dict[str, Any] = {
        "allowed_peer_agent_slugs": list(manifest.agent.allowed_peer_agent_slugs),
    }
    return {
        "agent_slug": manifest.slug,
        "display_name": manifest.display_name,
        "status": manifest.status,
        "backend_type": manifest.backend.type,
        "http_endpoint": manifest.resolve_http_endpoint(
            container_name=state.driver.container_name(manifest.slug),
        ),
        "metadata": metadata,
        "online": running and healthy,
        "runtime": runtime,
    }


def _issue_payloads(state: ServiceState) -> list[dict[str, Any]]:
    return [item.to_dict() for item in state.registry.issues()]


class ServiceReadOps:
    state: ServiceState

    async def health_snapshot(self) -> tuple[dict[str, Any], int]:
        summary = self.state.registry.summary()
        return {"status": "ok", "service": "orchestra_agents", **summary}, 200

    async def list_agents(self) -> dict[str, Any]:
        manifests = self.state.registry.manifests()
        statuses = await asyncio.gather(
            *(asyncio.to_thread(self.state.driver.status, manifest) for manifest in manifests),
            return_exceptions=False,
        )
        agents = [
            _agent_payload(manifest, runtime=status, state=self.state)
            for manifest, status in zip(manifests, statuses, strict=False)
        ]
        return {
            "success": True,
            "agents": agents,
            "count": len(agents),
            "issues": _issue_payloads(self.state),
        }

    async def get_agent(self, slug: str) -> dict[str, Any]:
        manifest = self.state.require_manifest(slug)
        status = await asyncio.to_thread(self.state.driver.status, manifest)
        return {
            "success": True,
            "agent": _agent_payload(manifest, runtime=status, state=self.state),
        }

    async def get_agent_status(self, slug: str) -> dict[str, Any]:
        manifest = self.state.require_manifest(slug)
        status = await asyncio.to_thread(self.state.driver.status, manifest)
        return {"success": True, "status": status}

    async def list_manifests(self) -> dict[str, Any]:
        manifests = [item.to_dict(include_path=True) for item in self.state.registry.manifests()]
        return {
            "success": True,
            "manifests_root": str(self.state.registry.manifests_root),
            "manifests": manifests,
            "count": len(manifests),
            "issues": _issue_payloads(self.state),
        }

    async def get_manifest(self, slug: str) -> dict[str, Any]:
        manifest = self.state.require_manifest(slug)
        return {"success": True, "manifest": manifest.to_dict(include_path=True)}
