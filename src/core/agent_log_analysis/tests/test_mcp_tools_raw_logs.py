"""Tests for MCP raw-log tool handlers."""

from __future__ import annotations

import unittest
from importlib import import_module
from typing import Protocol, cast

from core.agent_log_analysis.errors import ValidationError


class TestMCPToolsRawLogs(unittest.IsolatedAsyncioTestCase):
    """Verify MCP raw-log tool delegation and validation."""

    async def test_raw_logs_payload(self) -> None:
        runtime = _FakeRuntime()
        arguments: dict[str, object] = {"agent_slug": "agent-a", "limit": 2}
        result = await _tools().get_agent_raw_logs(runtime, arguments)
        self.assertEqual(runtime.calls, [("get_agent_raw_logs", arguments)])
        structured = cast(dict[str, object], result["structuredContent"])
        self.assertEqual(structured["agent_slug"], "agent-a")

    async def test_raw_logs_requires_agent(self) -> None:
        with self.assertRaises(ValidationError):
            await _tools().get_agent_raw_logs(_FakeRuntime(), {})


class _FakeRuntime:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def get_agent_raw_logs(self, payload: object) -> dict[str, object]:
        self.calls.append(("get_agent_raw_logs", payload))
        return {
            "agent_slug": "agent-a",
            "items": [
                {
                    "log_id": 1,
                    "event_id": "evt-1",
                    "occurred_at": "2025-01-01T00:00:00Z",
                    "received_at": "2025-01-01T00:00:01Z",
                    "agent_slug": "agent-a",
                    "run_id": "run-1",
                    "thread_id": "thread-1",
                    "correlation_id": "corr-1",
                    "source": "stdout",
                    "level": "INFO",
                    "raw_message": "message-1",
                    "raw_payload_json": {"idx": 1},
                },
            ],
            "next_cursor": None,
        }


class _RawLogToolsProtocol(Protocol):
    async def get_agent_raw_logs(
        self,
        runtime: _FakeRuntime,
        arguments: dict[str, object],
    ) -> dict[str, object]: ...


def _tools() -> _RawLogToolsProtocol:
    tools_module = import_module("core.agent_log_analysis.mcp_tools_raw_logs")
    return cast(_RawLogToolsProtocol, tools_module)
