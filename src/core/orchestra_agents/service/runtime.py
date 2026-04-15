from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any, cast

from aiohttp import web

from core.orchestra_agents.service_routes import register_service_routes
from core.orchestra_agents.service_state import ServiceState, ServiceStateDeps

if TYPE_CHECKING:
    from core.orchestra_agents._service_read_ops import ServiceReadOps as _ServiceReadOpsBase
    from core.orchestra_agents._service_write_ops import ServiceWriteOps as _ServiceWriteOpsBase
else:
    _ServiceReadOpsBase = cast(
        type[Any],
        import_module("core.orchestra_agents._service_read_ops").ServiceReadOps,
    )
    _ServiceWriteOpsBase = cast(
        type[Any],
        import_module("core.orchestra_agents._service_write_ops").ServiceWriteOps,
    )


class OrchestraAgentsService(_ServiceReadOpsBase, _ServiceWriteOpsBase):
    def __init__(self, state: ServiceState) -> None:
        self.state = state

    @classmethod
    def create(
        cls,
        *,
        manifests_root: str | None = None,
        deps: ServiceStateDeps | None = None,
    ) -> OrchestraAgentsService:
        return cls(
            ServiceState.create(
                manifests_root=manifests_root,
                deps=deps,
            )
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
