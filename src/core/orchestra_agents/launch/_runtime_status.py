"""Shared runtime status helpers for launch runtimes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol
from urllib import error as urlerror
from urllib import request as urlrequest

from core.orchestra_agents import _docker_driver_support as driver_support
from core.orchestra_agents.launch.launch_spec import LaunchSpec, RuntimeStatusPayload


class ProbeHealth(Protocol):
    def __call__(self, endpoint: str) -> dict[str, object]: ...


HealthResolution = driver_support.HealthResult


@dataclass(frozen=True)
class RuntimeStatusSupport:
    """Resolve runtime status payloads from Docker state and HTTP probes."""

    health_timeout_seconds: float

    def status(
        self,
        spec: LaunchSpec,
        *,
        state: dict[str, object] | None = None,
        probe_health: ProbeHealth | None = None,
        stderr: str = "",
    ) -> RuntimeStatusPayload:
        env = dict(spec.env)
        endpoint = env.get("ORCHESTRA_AGENT_HTTP_ENDPOINT") or None
        if state is None:
            return RuntimeStatusPayload(
                slug=spec.slug,
                container_name=spec.container_name,
                exists=False,
                running=False,
                healthy=False,
                backend_type=env.get("ORCHESTRA_AGENT_BACKEND_TYPE") or None,
                http_endpoint=endpoint,
                docker_status=None,
                health_status=None,
                started_at=None,
                last_error=_text(stderr),
            )
        return self._running_payload(spec, state, env, endpoint, probe_health or self._probe_health)

    def stopped_status(self, spec: LaunchSpec, *, removed: bool) -> RuntimeStatusPayload:
        env = dict(spec.env)
        return RuntimeStatusPayload(
            slug=spec.slug,
            container_name=spec.container_name,
            exists=not removed,
            running=False,
            healthy=False,
            backend_type=env.get("ORCHESTRA_AGENT_BACKEND_TYPE") or None,
            http_endpoint=env.get("ORCHESTRA_AGENT_HTTP_ENDPOINT") or None,
            docker_status=None,
            health_status=None,
            started_at=None,
            last_error=None,
        )

    def _running_payload(
        self,
        spec: LaunchSpec,
        state: dict[str, object],
        env: dict[str, str],
        endpoint: str | None,
        probe_health: ProbeHealth,
    ) -> RuntimeStatusPayload:
        health_status, healthy, last_error, running = self._resolve_health(
            state,
            endpoint=endpoint,
            probe_health=probe_health,
        )
        return RuntimeStatusPayload(
            slug=spec.slug,
            container_name=spec.container_name,
            exists=True,
            running=running,
            healthy=healthy,
            backend_type=env.get("ORCHESTRA_AGENT_BACKEND_TYPE") or None,
            http_endpoint=endpoint,
            docker_status=_text(state.get("Status")),
            health_status=health_status,
            started_at=_text(state.get("StartedAt")),
            last_error=last_error,
        )

    def _resolve_health(
        self,
        state: dict[str, object],
        *,
        endpoint: str | None,
        probe_health: ProbeHealth,
    ) -> HealthResolution:
        running = bool(state.get("Running"))
        if not running:
            return None, False, _text(state.get("Error")), False
        last_error = _text(state.get("Error"))
        docker_health = _docker_health_status(state)
        if docker_health == "healthy":
            return _docker_result(last_error, docker_health, healthy=True)
        if docker_health:
            return _docker_result(last_error, docker_health, healthy=False)
        if endpoint:
            return _probe_result(probe_health(endpoint), last_error)
        return None, False, last_error, True

    def _probe_health(self, endpoint: str) -> dict[str, object]:
        url = f"{endpoint.rstrip('/')}/healthz"
        try:
            payload = self._read_health_payload(url)
        except urlerror.HTTPError as error:
            return {
                "ok": False,
                "status_code": error.code,
                "error": error.reason,
            }
        except Exception as error:
            return {
                "ok": False,
                "status_code": None,
                "error": str(error),
            }
        if isinstance(payload, dict):
            return {
                "ok": True,
                "status_code": 200,
                "payload": payload,
            }
        return {
            "ok": True,
            "status_code": 200,
            "payload": {"raw": payload},
        }

    def _read_health_payload(self, url: str) -> object:
        with urlrequest.urlopen(url, timeout=self.health_timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8") or "{}")


def _docker_result(
    last_error: str | None,
    docker_health: str,
    *,
    healthy: bool,
) -> tuple[dict[str, object], bool, str | None, bool]:
    return (
        {
            "ok": healthy,
            "status_code": 200 if healthy else None,
            "source": "docker",
            "status": docker_health,
        },
        healthy,
        last_error if healthy else last_error or docker_health,
        True,
    )


def _probe_result(
    health_status: dict[str, object],
    last_error: str | None,
) -> tuple[dict[str, object], bool, str | None, bool]:
    healthy = bool(health_status.get("ok"))
    if not healthy and last_error is None:
        last_error = _text(health_status.get("error"))
    return health_status, healthy, last_error, True


def _docker_health_status(state: dict[str, object]) -> str:
    health_state = state.get("Health")
    if isinstance(health_state, dict):
        return str(health_state.get("Status") or "").strip().lower()
    return ""


def _text(value: object) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None
