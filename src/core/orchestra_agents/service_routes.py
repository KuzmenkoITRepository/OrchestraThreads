from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from aiohttp import web

from core.orchestra_agents.errors import ServiceError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Guarded:
    handler: Callable[[web.Request], Awaitable[web.Response]]

    async def __call__(self, request: web.Request) -> web.Response:
        try:
            return await self.handler(request)
        except ServiceError as exc:
            payload = {"success": False, "error": exc.message}
            return web.json_response(payload, status=exc.status)
        except Exception as exc:
            logger.warning("service route failed: %s", exc, exc_info=True)
            payload = {"success": False, "error": str(exc)}
            return web.json_response(payload, status=400)


class _RouteBase:
    def __init__(self, app_key: web.AppKey[Any]) -> None:
        self._app_key = app_key

    def _svc(self, request: web.Request) -> Any:
        return request.app[self._app_key]

    @staticmethod
    def _slug(request: web.Request) -> str:
        return request.match_info["slug"]


class _AgentReadRoutes(_RouteBase):
    async def health(self, request: web.Request) -> web.Response:
        payload, status = await self._svc(request).health_snapshot()
        return web.json_response(payload, status=status)

    async def list_agents(self, request: web.Request) -> web.Response:
        return web.json_response(await self._svc(request).list_agents())

    async def get_agent(self, request: web.Request) -> web.Response:
        result = await self._svc(request).get_agent(self._slug(request))
        return web.json_response(result)

    async def get_status(self, request: web.Request) -> web.Response:
        result = await self._svc(request).get_agent_status(self._slug(request))
        return web.json_response(result)

    def add_to(self, router: web.UrlDispatcher) -> None:
        router.add_get("/healthz", _Guarded(self.health))
        router.add_get("/api/v1/agents", _Guarded(self.list_agents))
        router.add_get("/api/v1/agents/{slug}", _Guarded(self.get_agent))
        router.add_get("/api/v1/agents/{slug}/status", _Guarded(self.get_status))


class _ManifestReadRoutes(_RouteBase):
    async def list_manifests(self, request: web.Request) -> web.Response:
        return web.json_response(await self._svc(request).list_manifests())

    async def get_manifest(self, request: web.Request) -> web.Response:
        result = await self._svc(request).get_manifest(self._slug(request))
        return web.json_response(result)

    def add_to(self, router: web.UrlDispatcher) -> None:
        router.add_get("/api/v1/manifests", _Guarded(self.list_manifests))
        router.add_get("/api/v1/manifests/{slug}", _Guarded(self.get_manifest))


class _WriteRoutes(_RouteBase):
    async def start(self, request: web.Request) -> web.Response:
        result = await self._svc(request).start_agent(self._slug(request))
        return web.json_response(result)

    async def stop(self, request: web.Request) -> web.Response:
        payload = await request.json() if request.can_read_body else {}
        remove = bool((payload or {}).get("remove", False))
        svc = self._svc(request)
        result = await svc.stop_agent(self._slug(request), remove=remove)
        return web.json_response(result)

    async def restart(self, request: web.Request) -> web.Response:
        result = await self._svc(request).restart_agent(self._slug(request))
        return web.json_response(result)

    async def validate(self, request: web.Request) -> web.Response:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ServiceError(400, "request body must be an object")
        result = await self._svc(request).validate_manifest_payload(payload)
        return web.json_response(result)

    async def reload(self, request: web.Request) -> web.Response:
        return web.json_response(await self._svc(request).reload_registry())

    def add_to(self, router: web.UrlDispatcher) -> None:
        router.add_post("/api/v1/agents/{slug}/start", _Guarded(self.start))
        router.add_post("/api/v1/agents/{slug}/stop", _Guarded(self.stop))
        router.add_post("/api/v1/agents/{slug}/restart", _Guarded(self.restart))
        router.add_post("/api/v1/manifests/validate", _Guarded(self.validate))
        router.add_post("/api/v1/registry/reload", _Guarded(self.reload))


def register_service_routes(router: web.UrlDispatcher, *, app_key: web.AppKey[Any]) -> None:
    _AgentReadRoutes(app_key).add_to(router)
    _ManifestReadRoutes(app_key).add_to(router)
    _WriteRoutes(app_key).add_to(router)
