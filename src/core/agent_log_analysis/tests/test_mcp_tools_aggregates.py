"""Tests for MCP aggregate tool handlers."""

from __future__ import annotations

import unittest
from importlib import import_module
from typing import Protocol, cast

from core.agent_log_analysis.errors import ValidationError


class TestMCPToolsAggregates(unittest.IsolatedAsyncioTestCase):
    """Verify MCP aggregate-tool delegation and validation."""

    async def test_aggregate_payload(self) -> None:
        runtime = _FakeRuntime()
        arguments: dict[str, object] = {"agent_slug": "agent-a", "group_by": ["status"]}
        result = await _tools().aggregate_agent_events(runtime, arguments)
        self.assertEqual(runtime.calls, [("aggregate_agent_events", arguments)])
        structured = cast(dict[str, object], result["structuredContent"])
        self.assertEqual(structured["agent_slug"], "agent-a")

    async def test_aggregate_requires_agent(self) -> None:
        with self.assertRaises(ValidationError):
            await _tools().aggregate_agent_events(_FakeRuntime(), {})


class _FakeRuntime:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def aggregate_agent_events(self, payload: object) -> dict[str, object]:
        self.calls.append(("aggregate_agent_events", payload))
        return {
            "agent_slug": "agent-a",
            "window_start": "2025-01-01T00:00:00Z",
            "window_end": "2025-01-01T01:00:00Z",
            "group_by": ["status"],
            "metrics": ["count"],
            "buckets": [{"keys": {"status": "success"}, "count": 1}],
        }


class _AggregateToolsProtocol(Protocol):
    async def aggregate_agent_events(
        self,
        runtime: _FakeRuntime,
        arguments: dict[str, object],
    ) -> dict[str, object]: ...


def _tools() -> _AggregateToolsProtocol:
    tools_module = import_module("core.agent_log_analysis.mcp.tools.aggregates")
    return cast(_AggregateToolsProtocol, tools_module)
