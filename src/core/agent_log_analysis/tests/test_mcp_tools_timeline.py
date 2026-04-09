"""Tests for MCP timeline tool handlers."""

from __future__ import annotations

import unittest
from importlib import import_module
from typing import Protocol, cast

from core.agent_log_analysis.errors import ValidationError


class TestMCPTimelineTools(unittest.IsolatedAsyncioTestCase):
    """Verify MCP timeline delegation and validation."""

    async def test_timeline_payload(self) -> None:
        runtime = _FakeRuntime()
        arguments: dict[str, object] = {"agent_slug": "agent-a", "limit": 2}
        result = await _tools().get_agent_timeline(runtime, arguments)
        self.assertEqual(runtime.calls, [("get_agent_timeline", arguments)])
        structured = cast(dict[str, object], result["structuredContent"])
        self.assertEqual(structured["agent_slug"], "agent-a")

    async def test_timeline_requires_agent(self) -> None:
        with self.assertRaises(ValidationError):
            await _tools().get_agent_timeline(_FakeRuntime(), {})


class _FakeRuntime:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def get_agent_timeline(self, payload: object) -> dict[str, object]:
        self.calls.append(("get_agent_timeline", payload))
        return {
            "agent_slug": "agent-a",
            "window_start": "2025-01-01T00:00:00Z",
            "window_end": "2025-01-01T01:00:00Z",
            "items": [{"event_id": "evt-1"}],
            "next_cursor": None,
        }


class _TimelineToolsProtocol(Protocol):
    async def get_agent_timeline(
        self,
        runtime: _FakeRuntime,
        arguments: dict[str, object],
    ) -> dict[str, object]: ...


def _tools() -> _TimelineToolsProtocol:
    tools_module = import_module("core.agent_log_analysis.mcp_tools_timeline")
    return cast(_TimelineToolsProtocol, tools_module)
