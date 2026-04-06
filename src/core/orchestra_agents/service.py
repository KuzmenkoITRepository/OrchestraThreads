from __future__ import annotations

import asyncio
from typing import Any

from aiohttp import web

from core.orchestra_agents.errors import ServiceError
from core.orchestra_agents.service_routes import register_service_routes
from core.orchestra_agents.service_state import ServiceState


class _ServiceReadOps:
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
            {
                "slug": manifest.slug,
                "display_name": manifest.display_name,
                "status": manifest.status,
                "backend_type": manifest.backend.type,
                "http_endpoint": manifest.resolve_http_endpoint(
                    container_name=self.state.driver.container_name(manifest.slug)
                ),
                "manifest": manifest.to_dict(include_path=True),
                "runtime": status,
            }
            for manifest, status in zip(manifests, statuses, strict=False)
        ]
        return {
            "success": True,
            "agents": agents,
            "count": len(agents),
            "issues": [item.to_dict() for item in self.state.registry.issues()],
        }

    async def get_agent(self, slug: str) -> dict[str, Any]:
        manifest = self.state.require_manifest(slug)
        status = await asyncio.to_thread(self.state.driver.status, manifest)
        return {
            "success": True,
            "agent": {
                "slug": manifest.slug,
                "display_name": manifest.display_name,
                "status": manifest.status,
                "backend_type": manifest.backend.type,
                "manifest": manifest.to_dict(include_path=True),
                "runtime": status,
            },
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
            "issues": [item.to_dict() for item in self.state.registry.issues()],
        }

    async def get_manifest(self, slug: str) -> dict[str, Any]:
        manifest = self.state.require_manifest(slug)
        return {"success": True, "manifest": manifest.to_dict(include_path=True)}


class _ServiceWriteOps:
    state: ServiceState

    async def start_agent(self, slug: str) -> dict[str, Any]:
        manifest = self.state.require_manifest(slug)
        async with self.state.lock:
            result = await asyncio.to_thread(self.state.driver.start, manifest)
        return {"success": True, "result": result}

    async def stop_agent(self, slug: str, *, remove: bool = False) -> dict[str, Any]:
        self.state.require_manifest(slug)
        async with self.state.lock:
            result = await asyncio.to_thread(self.state.driver.stop, slug, remove=remove)
        return {"success": True, "result": result}

    async def restart_agent(self, slug: str) -> dict[str, Any]:
        manifest = self.state.require_manifest(slug)
        async with self.state.lock:
            result = await asyncio.to_thread(self.state.driver.restart, manifest)
        return {"success": True, "result": result}

    async def validate_manifest_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        manifest_payload = payload.get("manifest")
        yaml_text = payload.get("yaml")
        if manifest_payload is None and yaml_text is None:
            raise ServiceError(400, "manifest or yaml is required")
        if manifest_payload is None:
            manifest = self.state.manifest_class.from_yaml_text(str(yaml_text or ""))
        elif isinstance(manifest_payload, dict):
            manifest = self.state.manifest_class.from_dict(manifest_payload)
        else:
            raise ServiceError(400, "manifest must be an object")
        return {"success": True, "manifest": manifest.to_dict(include_path=False)}

    async def reload_registry(self) -> dict[str, Any]:
        async with self.state.lock:
            self.state.registry.reload()
        return {"success": True, **self.state.registry.summary()}


class OrchestraAgentsService(_ServiceReadOps, _ServiceWriteOps):
    def __init__(self, state: ServiceState) -> None:
        self.state = state

    @classmethod
    def create(
        cls,
        *,
        manifests_root: str | None = None,
        registry: Any = None,
        driver: Any = None,
    ) -> OrchestraAgentsService:
        return cls(
            ServiceState.create(manifests_root=manifests_root, registry=registry, driver=driver)
        )


SERVICE_APP_KEY: web.AppKey[OrchestraAgentsService] = web.AppKey(
    "service",
    OrchestraAgentsService,
)


def build_app(service: OrchestraAgentsService) -> web.Application:
    app = web.Application()
    app[SERVICE_APP_KEY] = service
    register_service_routes(app.router, app_key=SERVICE_APP_KEY)
    return app
