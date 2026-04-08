"""Fake MCP server for SGR backend tests."""

from __future__ import annotations

import json
from typing import Any

from core.orchestra_agents.tests.template_helpers.sgr_fake_thread import FakeThreadService

_JsonDict = dict[str, Any]


class FakeToolMCPServer:
    """Fake MCP server that delegates tool calls to a FakeThreadService."""

    def __init__(self, thread_service: FakeThreadService) -> None:
        self._thread_service = thread_service

    async def handle_tools_call(
        self,
        name: str,
        arguments: _JsonDict,
    ) -> _JsonDict:
        """Route tool calls to the fake thread service."""
        if name == "thread_send":
            return _mcp_send(self._thread_service, arguments)
        if name == "thread_status":
            return _mcp_status(self._thread_service, arguments)
        return _fake_mcp_result({"ok": True})

    async def close(self) -> None:
        """No-op close."""


def _mcp_send(service: FakeThreadService, arguments: _JsonDict) -> _JsonDict:
    msg = str(arguments.get("message") or "")
    service.message_calls.append(arguments)
    return _fake_mcp_result({"ok": True, "message": msg, "route": "auto"})


def _mcp_status(service: FakeThreadService, arguments: _JsonDict) -> _JsonDict:
    service.notification_calls.append(arguments)
    published = str(arguments.get("status") or "")
    return _fake_mcp_result({"ok": True, "published_status": published})


def _fake_mcp_result(structured: _JsonDict) -> _JsonDict:
    return {
        "content": [{"type": "text", "text": json.dumps(structured)}],
        "structuredContent": structured,
    }
