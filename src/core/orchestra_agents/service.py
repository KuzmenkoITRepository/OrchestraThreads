"""HTTP lifecycle service for manifest-defined Orchestra agents."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

from aiohttp import web

from .docker_driver import DockerDriver
from .errors import ServiceError
from .manifest import AgentManifest
from .registry import AgentManifestRegistry


logger = logging.getLogger(__name__)
SERVICE_APP_KEY = web.AppKey("service", "OrchestraAgentsService")


def _json_error(message: str, *, status: int) -> web.Response:
    return web.json_response({"success": False, "error": message}, status=status)


class OrchestraAgentsService:
    """Own manifests and expose Docker lifecycle operations over HTTP."""

    def __init__(
        self,
        *,
        manifests_root: Optional[str] = None,
        registry: Optional[AgentManifestRegistry] = None,
        driver: Optional[DockerDriver] = None,
    ) -> None:
        self.registry = registry or AgentManifestRegistry(manifests_root=manifests_root)
        self.driver = driver or DockerDriver(manifests_root=self.registry.manifests_root)
        self._lock = asyncio.Lock()

    async def health_snapshot(self) -> tuple[dict[str, Any], int]:
        summary = self.registry.summary()
        payload = {
            "status": "ok",
            "service": "orchestra_agents",
            **summary,
        }
        return payload, 200

    async def list_agents(self) -> dict[str, Any]:
        manifests = self.registry.manifests()
        statuses = await asyncio.gather(
            *(asyncio.to_thread(self.driver.status, manifest) for manifest in manifests),
            return_exceptions=False,
        )
        agents = []
        for manifest, status in zip(manifests, statuses):
            agents.append(
                {
                    "slug": manifest.slug,
                    "display_name": manifest.display_name,
                    "status": manifest.status,
                    "backend_type": manifest.backend.type,
                    "http_endpoint": manifest.resolve_http_endpoint(
                        container_name=self.driver.container_name(manifest.slug)
                    ),
                    "manifest": manifest.to_dict(include_path=True),
                    "runtime": status,
                }
            )
        return {
            "success": True,
            "agents": agents,
            "count": len(agents),
            "issues": [item.to_dict() for item in self.registry.issues()],
        }

    async def get_agent(self, slug: str) -> dict[str, Any]:
        manifest = self._require_manifest(slug)
        status = await asyncio.to_thread(self.driver.status, manifest)
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
        manifest = self._require_manifest(slug)
        status = await asyncio.to_thread(self.driver.status, manifest)
        return {
            "success": True,
            "status": status,
        }

    async def start_agent(self, slug: str) -> dict[str, Any]:
        manifest = self._require_manifest(slug)
        async with self._lock:
            result = await asyncio.to_thread(self.driver.start, manifest)
        return {
            "success": True,
            "result": result,
        }

    async def stop_agent(self, slug: str, *, remove: bool = False) -> dict[str, Any]:
        self._require_manifest(slug)
        async with self._lock:
            result = await asyncio.to_thread(self.driver.stop, slug, remove=remove)
        return {
            "success": True,
            "result": result,
        }

    async def restart_agent(self, slug: str) -> dict[str, Any]:
        manifest = self._require_manifest(slug)
        async with self._lock:
            result = await asyncio.to_thread(self.driver.restart, manifest)
        return {
            "success": True,
            "result": result,
        }

    async def list_manifests(self) -> dict[str, Any]:
        manifests = [item.to_dict(include_path=True) for item in self.registry.manifests()]
        return {
            "success": True,
            "manifests_root": str(self.registry.manifests_root),
            "manifests": manifests,
            "count": len(manifests),
            "issues": [item.to_dict() for item in self.registry.issues()],
        }

    async def get_manifest(self, slug: str) -> dict[str, Any]:
        manifest = self._require_manifest(slug)
        return {
            "success": True,
            "manifest": manifest.to_dict(include_path=True),
        }

    async def validate_manifest_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ServiceError(400, "request body must be an object")
        manifest_payload = payload.get("manifest")
        yaml_text = payload.get("yaml")
        if manifest_payload is None and yaml_text is None:
            raise ServiceError(400, "manifest or yaml is required")
        try:
            if manifest_payload is not None:
                if not isinstance(manifest_payload, dict):
                    raise ServiceError(400, "manifest must be an object")
                manifest = AgentManifest.from_dict(manifest_payload)
            else:
                manifest = AgentManifest.from_yaml_text(str(yaml_text or ""))
        except ServiceError:
            raise
        except Exception as exc:
            raise ServiceError(400, str(exc)) from exc
        return {
            "success": True,
            "manifest": manifest.to_dict(include_path=False),
        }

    async def reload_registry(self) -> dict[str, Any]:
        async with self._lock:
            self.registry.reload()
        return {
            "success": True,
            **self.registry.summary(),
        }

    def _require_manifest(self, slug: str) -> AgentManifest:
        normalized = str(slug or "").strip()
        if not normalized:
            raise ServiceError(400, "slug is required")
        try:
            return self.registry.require(normalized)
        except KeyError as exc:
            raise ServiceError(404, str(exc)) from exc


def build_app(service: OrchestraAgentsService) -> web.Application:
    app = web.Application()
    app[SERVICE_APP_KEY] = service

    async def handle_health(_: web.Request) -> web.Response:
        payload, status = await service.health_snapshot()
        return web.json_response(payload, status=status)

    async def handle_list_agents(_: web.Request) -> web.Response:
        try:
            return web.json_response(await service.list_agents())
        except ServiceError as exc:
            return _json_error(exc.message, status=exc.status)

    async def handle_get_agent(request: web.Request) -> web.Response:
        try:
            return web.json_response(await service.get_agent(request.match_info["slug"]))
        except ServiceError as exc:
            return _json_error(exc.message, status=exc.status)

    async def handle_get_agent_status(request: web.Request) -> web.Response:
        try:
            return web.json_response(await service.get_agent_status(request.match_info["slug"]))
        except ServiceError as exc:
            return _json_error(exc.message, status=exc.status)

    async def handle_start_agent(request: web.Request) -> web.Response:
        try:
            return web.json_response(await service.start_agent(request.match_info["slug"]))
        except ServiceError as exc:
            return _json_error(exc.message, status=exc.status)
        except Exception as exc:
            logger.warning("agent start failed: %s", exc, exc_info=True)
            return _json_error(str(exc), status=400)

    async def handle_stop_agent(request: web.Request) -> web.Response:
        payload = await request.json() if request.can_read_body else {}
        try:
            return web.json_response(
                await service.stop_agent(
                    request.match_info["slug"],
                    remove=bool((payload or {}).get("remove", False)),
                )
            )
        except ServiceError as exc:
            return _json_error(exc.message, status=exc.status)
        except Exception as exc:
            logger.warning("agent stop failed: %s", exc, exc_info=True)
            return _json_error(str(exc), status=400)

    async def handle_restart_agent(request: web.Request) -> web.Response:
        try:
            return web.json_response(await service.restart_agent(request.match_info["slug"]))
        except ServiceError as exc:
            return _json_error(exc.message, status=exc.status)
        except Exception as exc:
            logger.warning("agent restart failed: %s", exc, exc_info=True)
            return _json_error(str(exc), status=400)

    async def handle_list_manifests(_: web.Request) -> web.Response:
        try:
            return web.json_response(await service.list_manifests())
        except ServiceError as exc:
            return _json_error(exc.message, status=exc.status)

    async def handle_get_manifest(request: web.Request) -> web.Response:
        try:
            return web.json_response(await service.get_manifest(request.match_info["slug"]))
        except ServiceError as exc:
            return _json_error(exc.message, status=exc.status)

    async def handle_validate_manifest(request: web.Request) -> web.Response:
        payload = await request.json()
        try:
            return web.json_response(await service.validate_manifest_payload(payload))
        except ServiceError as exc:
            return _json_error(exc.message, status=exc.status)

    async def handle_reload_registry(_: web.Request) -> web.Response:
        try:
            return web.json_response(await service.reload_registry())
        except ServiceError as exc:
            return _json_error(exc.message, status=exc.status)

    app.router.add_get("/healthz", handle_health)
    app.router.add_get("/api/v1/agents", handle_list_agents)
    app.router.add_get("/api/v1/agents/{slug}", handle_get_agent)
    app.router.add_get("/api/v1/agents/{slug}/status", handle_get_agent_status)
    app.router.add_post("/api/v1/agents/{slug}/start", handle_start_agent)
    app.router.add_post("/api/v1/agents/{slug}/stop", handle_stop_agent)
    app.router.add_post("/api/v1/agents/{slug}/restart", handle_restart_agent)
    app.router.add_get("/api/v1/manifests", handle_list_manifests)
    app.router.add_get("/api/v1/manifests/{slug}", handle_get_manifest)
    app.router.add_post("/api/v1/manifests/validate", handle_validate_manifest)
    app.router.add_post("/api/v1/registry/reload", handle_reload_registry)
    return app
