from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from core.orchestra_agents.errors import ServiceError

if TYPE_CHECKING:
    from core.orchestra_agents.service_state import ServiceState


def _validated_manifest_input(payload: dict[str, Any]) -> tuple[Any, Any]:
    manifest_payload = payload.get("manifest")
    yaml_text = payload.get("yaml")
    if manifest_payload is None and yaml_text is None:
        raise ServiceError(400, "manifest or yaml is required")
    return manifest_payload, yaml_text


class ServiceWriteOps:
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
        manifest_payload, yaml_text = _validated_manifest_input(payload)
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
