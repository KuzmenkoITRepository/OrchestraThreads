"""Tests for MCP correlation tool handlers."""

from __future__ import annotations

import unittest
from importlib import import_module
from typing import Protocol, cast

from core.agent_log_analysis.errors import ValidationError


class TestMCPCorrelationTools(unittest.IsolatedAsyncioTestCase):
    """Verify MCP correlation delegation and validation."""

    async def test_correlation_payload(self) -> None:
        runtime = _FakeRuntime()
        arguments: dict[str, object] = {
            "agent_slug": "agent-a",
            "correlation_id": "corr-1",
        }
        result = await _tools().get_agent_correlation_chain(runtime, arguments)
        self.assertEqual(runtime.calls, [("get_agent_correlation_chain", arguments)])
        structured = cast(dict[str, object], result["structuredContent"])
        self.assertEqual(structured["correlation_id"], "corr-1")

    async def test_correlation_requires_scope(self) -> None:
        with self.assertRaises(ValidationError):
            await _tools().get_agent_correlation_chain(
                _FakeRuntime(),
                {"agent_slug": "agent-a"},
            )


class _FakeRuntime:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def get_agent_correlation_chain(self, payload: object) -> dict[str, object]:
        self.calls.append(("get_agent_correlation_chain", payload))
        return {
            "agent_slug": "agent-a",
            "correlation_id": "corr-1",
            "items": [{"event_id": "evt-1"}],
            "truncated": False,
        }


class _CorrelationToolsProtocol(Protocol):
    async def get_agent_correlation_chain(
        self,
        runtime: _FakeRuntime,
        arguments: dict[str, object],
    ) -> dict[str, object]: ...


def _tools() -> _CorrelationToolsProtocol:
    tools_module = import_module("core.agent_log_analysis.mcp_tools_timeline")
    return cast(_CorrelationToolsProtocol, tools_module)
