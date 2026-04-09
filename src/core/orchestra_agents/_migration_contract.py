"""Runtime contract probing for backend switch verification."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from types import MappingProxyType
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

from core.orchestra_agents.manifest import AgentManifest

_PROBE_TIMEOUT_SECONDS = 2.0
_SWITCH_REQUESTED_BY = "task12-switch-verifier"


def probe_runtime_contract(
    manifest: AgentManifest,
    *,
    container_name: str,
    probe: Callable[
        [str, str, dict[str, Any] | None],
        dict[str, Any],
    ],
) -> dict[str, Any]:
    """Probe all contract endpoints for a switched agent."""
    base_url = manifest.resolve_http_endpoint(
        container_name=container_name,
    ).rstrip("/")
    checks = _collect_checks(base_url, probe)
    return {
        "ok": all(_check_ok(name, resp) for name, resp in checks.items()),
        "base_url": base_url,
        "checks": checks,
    }


def default_contract_probe(
    url: str,
    method: str,
    payload: dict[str, Any] | None,
) -> dict[str, Any]:
    """HTTP probe with timeout for contract verification."""
    encoded = json.dumps(payload).encode() if payload else None
    headers = (
        {}
        if encoded is None
        else {
            "Content-Type": "application/json",
        }
    )
    req = urlrequest.Request(
        url,
        data=encoded,
        headers=headers,
        method=method,
    )
    try:
        with urlrequest.urlopen(
            req,
            timeout=_PROBE_TIMEOUT_SECONDS,
        ) as resp:
            body = resp.read().decode("utf-8")
            return {
                "ok": 200 <= resp.status < 300,
                "status_code": resp.status,
                "payload": _parse_json_body(body),
            }
    except urlerror.URLError as exc:
        return {
            "ok": False,
            "status_code": None,
            "error": str(exc),
            "payload": {},
        }


def status_ok(status_result: dict[str, Any]) -> bool:
    """Check if an agent status result indicates healthy running."""
    return (
        bool(status_result.get("exists"))
        and bool(status_result.get("running"))
        and bool(status_result.get("healthy"))
    )


def event_probe_payload(agent_slug: str) -> dict[str, Any]:
    """Build a minimal event probe payload for switch verification."""
    delivery_id = f"switch-verify-{time.time_ns()}"
    return {
        "delivery_id": delivery_id,
        "events": [
            {
                "event_id": f"{delivery_id}-evt",
                "thread_id": "switch-verify-thread",
                "event_kind": "message",
                "from_agent_slug": "secretary",
                "to_agent_slug": agent_slug,
                "message_text": "backend switch verification",
            },
        ],
    }


def _collect_checks(
    base_url: str,
    probe: Callable[
        [str, str, dict[str, Any] | None],
        dict[str, Any],
    ],
) -> dict[str, dict[str, Any]]:
    return {
        "healthz": probe(f"{base_url}/healthz", "GET", None),
        "last_status": probe(
            f"{base_url}/last_status",
            "GET",
            None,
        ),
        "clear_context": probe(
            f"{base_url}/clear_context",
            "POST",
            {"requested_by": _SWITCH_REQUESTED_BY},
        ),
        "stop": probe(
            f"{base_url}/stop",
            "POST",
            {"reason": _SWITCH_REQUESTED_BY},
        ),
        "event": probe(
            f"{base_url}/event",
            "POST",
            event_probe_payload(base_url.rsplit("/", 1)[-1]),
        ),
    }


_PAYLOAD_KEY: MappingProxyType[str, str | None] = MappingProxyType(
    {
        "healthz": "ok",
        "last_status": None,
        "clear_context": "success",
        "stop": "success",
        "event": "accepted",
    }
)


def _check_ok(
    name: str,
    response: dict[str, Any],
) -> bool:
    if not bool(response.get("ok")):
        return False
    payload = response.get("payload")
    if not isinstance(payload, dict):
        return False
    key = _PAYLOAD_KEY.get(name)
    if key is None:
        return name == "last_status"
    return bool(payload.get(key))


def _parse_json_body(body: str) -> dict[str, Any]:
    if not body.strip():
        return {}
    loaded = json.loads(body)
    if isinstance(loaded, dict):
        return dict(loaded)
    return {"value": loaded}
