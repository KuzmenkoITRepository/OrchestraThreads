from __future__ import annotations

import json
import pathlib
import socket
import unittest
from collections.abc import Awaitable, Callable
from typing import Any, cast

from core.orchestra_agents import runtime as runtime_contract
from core.orchestra_agents.tests.template_helpers.fixture import TemplateFixture


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


async def _wait_for(predicate: Callable[[], object], *, timeout: float = 5.0) -> object:
    import asyncio
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        await asyncio.sleep(0.05)
    return None


def _build_backend(
    fixture: TemplateFixture,
    *,
    require_tool_call_for_response: bool = False,
    include_mcp_server: bool = False,
    max_attempts: int = 2,
) -> Any:
    mcp_servers = []
    if include_mcp_server:
        mcp_servers = [
            {
                "name": "orchestra_threads",
                "command": "python",
                "args": ["-m", "core.orchestra_thread.mcp_server"],
                "cwd": "{working_dir}",
                "startup_timeout_sec": 15,
                "required": False,
                "enabled": True,
                "enabled_tools": [
                    "thread_send",
                    "thread_status",
                    "thread_current",
                    "thread_expand",
                    "thread_guide",
                ],
                "env": {
                    "ORCHESTRA_THREADS_AGENT_SLUG": "{agent_slug}",
                    "ORCHESTRA_THREADS_URL": "http://127.0.0.1:8788",
                    "ORCHESTRA_THREADS_ACTIVE_CONTEXT_PATH": "{active_context_path}",
                    "PYTHONPATH": "{pythonpath}",
                },
            },
            {
                "name": "orchestra_memory",
                "command": "python",
                "args": ["-m", "core.orchestra_memory.mcp_server"],
                "cwd": "{working_dir}",
                "startup_timeout_sec": 15,
                "required": False,
                "enabled": True,
                "enabled_tools": [
                    "memory_remember",
                    "memory_search",
                    "memory_delete",
                    "memory_clear",
                ],
                "env": {
                    "ORCHESTRA_AGENT_SLUG": "{agent_slug}",
                    "ORCHESTRA_MEMORY_URL": "http://127.0.0.1:8793",
                    "PYTHONPATH": "{pythonpath}",
                },
            },
        ]
    return fixture.backend_class(
        agent_slug="generic_worker",
        backend_type="agent_mux",
        working_dir=str(fixture.agent_dir),
        config={
            "llm_proxy_url": f"http://127.0.0.1:{_free_port()}",
            "llm_proxy_api_key": "llm-proxy-key",
            "llm_route_policy": "codex_only",
            "model": "cx/gpt-5.1-codex-mini",
            "agent_mux_binary": str(fixture.agent_mux_binary),
            "state_root": str(fixture.root / "runtime_state"),
            "max_attempts": max_attempts,
            "require_tool_call_for_response": require_tool_call_for_response,
            "mcp_servers": mcp_servers,
        },
        system_prompt="Use configured tools for external actions.",
        http_endpoint="http://orchestra-agent-generic_worker:8787",
    )


async def _start_backend(
    test_case: unittest.IsolatedAsyncioTestCase,
    fixture: TemplateFixture,
    *,
    require_tool_call_for_response: bool = False,
    include_mcp_server: bool = False,
    max_attempts: int = 2,
) -> Any:
    backend = _build_backend(
        fixture,
        require_tool_call_for_response=require_tool_call_for_response,
        include_mcp_server=include_mcp_server,
        max_attempts=max_attempts,
    )
    await backend.on_start()
    test_case.addAsyncCleanup(backend.on_shutdown)
    return backend


async def _run_backend_once(
    fixture: TemplateFixture,
    action: Callable[[Any], Awaitable[Any]],
) -> Any:
    backend = _build_backend(fixture)
    await backend.on_start()
    try:
        result = await action(backend)
    except BaseException:
        await backend.on_shutdown()
        raise
    await backend.on_shutdown()
    return result


def _delivery(
    *,
    event_id: str = "event-1",
    message_text: str = "Prepare the update.",
) -> runtime_contract.EventDelivery:
    return runtime_contract.EventDelivery.from_dict(
        {
            "delivery_id": f"delivery-{event_id}",
            "events": [
                {
                    "event_id": event_id,
                    "event_kind": "telegram_message",
                    "thread_id": None,
                    "root_thread_id": None,
                    "parent_thread_id": None,
                    "owner_agent_slug": None,
                    "sequence_no": None,
                    "notification_status": None,
                    "from_agent_slug": "telegram_ingress",
                    "to_agent_slug": "generic_worker",
                    "message_text": message_text,
                    "interrupts_runtime": True,
                    "requires_response": True,
                    "created_at": "2026-04-03T07:00:00Z",
                    "source_context": {
                        "channel": "telegram",
                        "chat_title": "Owner DM",
                        "sender_display": "Owner",
                        "received_at": "2026-04-03T07:00:00Z",
                    },
                }
            ],
        }
    )


def _read_capture(capture_path: pathlib.Path) -> dict[str, Any]:
    payload = json.loads(capture_path.read_text(encoding="utf-8"))
    return cast(dict[str, Any], payload)
