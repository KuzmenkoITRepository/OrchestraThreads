"""Tests for MCP event tool handlers."""

from __future__ import annotations

import unittest

from core.agent_log_analysis.errors import ValidationError
from core.agent_log_analysis.mcp.tools.events import get_event, query_agent_events


class TestMCPToolsEvents(unittest.IsolatedAsyncioTestCase):
    """Verify MCP event-tool delegation and validation."""

    async def test_get_event_delegates_and_wraps_payload(self) -> None:
        runtime = _FakeRuntime()
        result = await get_event(runtime, {"event_id": "evt-1"})
        self.assertEqual(runtime.calls, [("get_event", "evt-1")])
        self.assertEqual(result["structuredContent"]["event"]["event_id"], "evt-1")

    async def test_get_event_requires_event_id(self) -> None:
        with self.assertRaises(ValidationError):
            await get_event(_FakeRuntime(), {})

    async def test_query_agent_events_delegates_payload(self) -> None:
        runtime = _FakeRuntime()
        arguments = {"agent_slug": "agent-a", "limit": 2}
        result = await query_agent_events(runtime, arguments)
        self.assertEqual(runtime.calls, [("query_agent_events", arguments)])
        self.assertEqual(result["structuredContent"]["agent_slug"], "agent-a")

    async def test_query_events_error(self) -> None:
        runtime = _FakeRuntime(
            error=ValidationError("AGENT_SCOPE_REQUIRED", "agent_slug is required")
        )
        with self.assertRaises(ValidationError):
            await query_agent_events(runtime, {})


class _FakeRuntime:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[tuple[str, object]] = []
        self.error = error

    async def get_event(self, event_id: str) -> dict[str, object]:
        if self.error is not None:
            raise self.error
        self.calls.append(("get_event", event_id))
        return {"event": {"event_id": event_id}}

    async def query_agent_events(self, payload: object) -> dict[str, object]:
        if self.error is not None:
            raise self.error
        self.calls.append(("query_agent_events", payload))
        return {"agent_slug": "agent-a", "items": [], "next_cursor": None}
