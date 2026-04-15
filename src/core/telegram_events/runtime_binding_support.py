from __future__ import annotations

from typing import Any

from core.orchestra_thread.client import OrchestraThreadsClient
from core.telegram_events.service.runtime_models import (
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


def runtime_resource_config(service: Any) -> RuntimeResourceConfig:
    return RuntimeResourceConfig(
        http_host=service._http_host,
        http_port=service._http_port,
        threads_url=service._threads_url,
        agent_slug=service._agent_slug,
        agent_registry=service._agent_registry,
        register_agent=service.register_agent,
    )


def apply_runtime_resources(
    service: Any,
    runtime_resources: RuntimeResources,
) -> None:
    service._shutdown_future = runtime_resources.shutdown_future
    service._http_client = runtime_resources.http_client
    service._threads_client = runtime_resources.threads_client
    service._http_runner = runtime_resources.http_runner
    service._heartbeat_task = runtime_resources.heartbeat_task


def registration_base_url(service: Any) -> str:
    if service._public_base_url:
        return str(service._public_base_url)
    runner_url = _runner_base_url(service._http_runner)
    if runner_url is not None:
        return runner_url
    return f"http://{service._http_host}:{service._http_port}"


async def register_with_threads(service: Any) -> None:
    threads_client = require_threads_client(service._threads_client)
    await threads_client.register_agent(
        agent_slug=service._agent_slug,
        display_name=service._agent_slug,
        base_url=registration_base_url(service),
        metadata={
            "kind": "telegram-events-service",
            "backend_type": "telegram-events",
            "tool_surface": "telegram-events-ingress",
        },
    )


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
