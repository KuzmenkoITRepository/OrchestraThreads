from __future__ import annotations

from typing import Any

from core.orchestra_thread.client import OrchestraThreadsClient
from core.telegram_events.service.runtime_support import (
    RuntimeResourceConfig,
    RuntimeResources,
)


def require_threads_client(client: OrchestraThreadsClient | None) -> OrchestraThreadsClient:
    if client is None:
        raise RuntimeError("OrchestraThreads client not initialized")
    return client


def extract_thread_id(response: dict[str, Any]) -> str:
    thread_payload = response.get("thread")
    if not isinstance(thread_payload, dict):
        raise RuntimeError("orchestra-thread send_message response missing thread payload")
    thread_id = str(thread_payload.get("thread_id") or "").strip()
    if not thread_id:
        raise RuntimeError("orchestra-thread send_message response missing thread_id")
    return thread_id


def normalized_public_base_url(options: dict[str, Any]) -> str:
    return str(options.get("public_base_url", "")).strip().rstrip("/")


def runtime_resource_config(service: Any) -> RuntimeResourceConfig:
    return RuntimeResourceConfig(
        events_url=service._events_url,
        bearer_token=service._bearer_token,
        http_host=service._http_host,
        http_port=service._http_port,
        relay_url=service._mcp_url,
        threads_url=service._threads_url,
        agent_slug=service._agent_slug,
    )


def apply_runtime_resources(
    service: Any,
    runtime_resources: RuntimeResources,
) -> None:
    service._shutdown_future = runtime_resources.shutdown_future
    service._http_client = runtime_resources.http_client
    service._threads_client = runtime_resources.threads_client
    service._consumer = runtime_resources.consumer
    service._http_runner = runtime_resources.http_runner
    service._heartbeat_task = runtime_resources.heartbeat_task


def registration_base_url(service: Any) -> str:
    if service._public_base_url:
        return str(service._public_base_url)
    runner_url = _runner_base_url(service._http_runner)
    if runner_url is not None:
        return runner_url
    return f"http://{service._http_host}:{service._http_port}"


def _runner_base_url(runner: Any) -> str | None:
    if runner is None:
        return None
    for site in runner.sites:
        server = getattr(site, "_server", None)
        sockets = getattr(server, "sockets", None)
        if not sockets:
            continue
        socket_info = sockets[0].getsockname()
        runner_url = f"http://{socket_info[0]}:{socket_info[1]}"
        if runner_url is not None:
            return runner_url
    return None
