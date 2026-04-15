from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import import_module
from typing import Any, cast

from core.orchestra_agents.manifest import AgentManifest
from core.orchestra_agents.registry import AgentManifestRegistry

_service_constants = import_module("core.orchestra_agents.tests._service_test_constants")
_runtime_support = import_module("core.orchestra_agents.tests._service_test_runtime_support")
STATUS_RUNNING = _service_constants.STATUS_RUNNING
compute_is_running = _runtime_support.compute_is_running
public_field_names = _runtime_support.public_field_names


@dataclass(frozen=True)
class FakeLaunchSpec:
    slug: str
    backend_type: str
    http_endpoint_template: str
    container_name: str


class FakeBuilder:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def build(self, manifest: AgentManifest) -> FakeLaunchSpec:
        self.events.append(f"build:{manifest.slug}")
        return FakeLaunchSpec(
            slug=manifest.slug,
            backend_type=manifest.backend.type,
            http_endpoint_template=manifest.agent.http_endpoint,
            container_name=f"orchestra-agent-{manifest.slug}",
        )


@dataclass
class RuntimeCalls:
    started: list[str] = field(default_factory=list)
    stopped: list[tuple[str, bool]] = field(default_factory=list)
    restarted: list[str] = field(default_factory=list)
    status_calls: list[str] = field(default_factory=list)
    container_name_calls: list[str] = field(default_factory=list)


class FakeRuntime:
    def __init__(self, name: str, events: list[str]) -> None:
        self.name = name
        self.events = events
        self.calls = RuntimeCalls()

    def container_name(self, spec: FakeLaunchSpec) -> str:
        self.events.append(f"runtime.container_name:{self.name}:{spec.slug}")
        self.calls.container_name_calls.append(spec.slug)
        return spec.container_name

    def status(self, spec: FakeLaunchSpec) -> dict[str, Any]:
        self.events.append(f"runtime.status:{self.name}:{spec.slug}")
        self.calls.status_calls.append(spec.slug)
        return self._status_payload(spec)

    def start(self, spec: FakeLaunchSpec) -> dict[str, Any]:
        self.events.append(f"runtime.start:{self.name}:{spec.slug}")
        self.calls.started.append(spec.slug)
        return self._status_payload(spec, running=True)

    def stop(self, spec: FakeLaunchSpec, *, remove: bool = False) -> dict[str, Any]:
        self.events.append(f"runtime.stop:{self.name}:{spec.slug}:remove={remove}")
        self.calls.stopped.append((spec.slug, remove))
        return {
            "slug": spec.slug,
            "container_name": spec.container_name,
            "exists": not remove,
            STATUS_RUNNING: False,
            "removed": remove,
            "runtime_name": self.name,
        }

    def restart(self, spec: FakeLaunchSpec) -> dict[str, Any]:
        self.events.append(f"runtime.restart:{self.name}:{spec.slug}")
        self.calls.restarted.append(spec.slug)
        return self._status_payload(spec, running=True)

    def _status_payload(
        self,
        spec: FakeLaunchSpec,
        *,
        running: bool | None = None,
    ) -> dict[str, Any]:
        return {
            "slug": spec.slug,
            "container_name": spec.container_name,
            "exists": True,
            STATUS_RUNNING: compute_is_running(
                spec=spec,
                started=self.calls.started,
                restarted=self.calls.restarted,
                running=running,
            ),
            "healthy": True,
            "backend_type": spec.backend_type,
            "http_endpoint": spec.http_endpoint_template.replace(
                "orchestra-agent-coding_agent",
                spec.container_name,
            ),
            "docker_status": STATUS_RUNNING,
            "health_status": {"ok": True},
            "started_at": "2025-01-01T00:00:00Z",
            "last_error": None,
            "runtime_name": self.name,
        }


class _DriverCompatibilityAdapter:
    def __init__(self, state: FakeServiceState) -> None:
        self._state = state

    def container_name(self, slug: str) -> str:
        manifest = self._state.require_manifest(slug)
        spec = self._state.builder.build(manifest)
        runtime = self._state.resolve_runtime(spec, operation="container_name")
        return runtime.container_name(spec)

    def status(self, manifest: AgentManifest) -> dict[str, Any]:
        spec = self._state.builder.build(manifest)
        runtime = self._state.resolve_runtime(spec, operation="status")
        return runtime.status(spec)

    def start(self, manifest: AgentManifest) -> dict[str, Any]:
        spec = self._state.builder.build(manifest)
        runtime = self._state.resolve_runtime(spec, operation="start")
        return runtime.start(spec)

    def stop(self, slug: str, *, remove: bool = False) -> dict[str, Any]:
        manifest = self._state.require_manifest(slug)
        spec = self._state.builder.build(manifest)
        runtime = self._state.resolve_runtime(spec, operation="stop")
        return runtime.stop(spec, remove=remove)

    def restart(self, manifest: AgentManifest) -> dict[str, Any]:
        spec = self._state.builder.build(manifest)
        runtime = self._state.resolve_runtime(spec, operation="restart")
        return runtime.restart(spec)


RuntimeSelector = Callable[[FakeLaunchSpec, str, FakeRuntime], FakeRuntime]


@dataclass
class FakeServiceState:
    registry: AgentManifestRegistry
    builder: FakeBuilder
    default_runtime: FakeRuntime
    runtime_selector: RuntimeSelector | None = None
    manifest_class: type[AgentManifest] = AgentManifest
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _driver: _DriverCompatibilityAdapter = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._driver = _DriverCompatibilityAdapter(self)

    @property
    def driver(self) -> _DriverCompatibilityAdapter:
        return self._driver

    def require_manifest(self, slug: str) -> AgentManifest:
        return self.registry.require(slug)

    def build_spec(self, manifest: AgentManifest) -> FakeLaunchSpec:
        return self.builder.build(manifest)

    def resolve_runtime(self, spec: FakeLaunchSpec, *, operation: str) -> FakeRuntime:
        runtime = self.default_runtime
        if self.runtime_selector is not None:
            runtime = self.runtime_selector(spec, operation, self.default_runtime)
        self.builder.events.append(f"select_runtime:{runtime.name}:{operation}:{spec.slug}")
        return runtime


def public_service_state_fields() -> set[str]:
    return cast(set[str], public_field_names(FakeServiceState))
