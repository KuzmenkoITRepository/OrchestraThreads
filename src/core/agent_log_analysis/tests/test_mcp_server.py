"""Tests for the agent-log-analysis MCP server."""

from __future__ import annotations

import unittest

from core.agent_log_analysis.errors import ValidationError
from core.agent_log_analysis.mcp_server import AgentLogAnalysisMCPServer

REQUEST_MAP = dict[str, object]


class TestMCPServerSurface(unittest.IsolatedAsyncioTestCase):
    """Verify MCP server registration and happy-path routing."""

    async def test_initialize_and_tools_list(self) -> None:
        server = AgentLogAnalysisMCPServer(runtime=_FakeRuntime())
        initialize = await server.handle_request(_request("1", "initialize", {}))
        assert initialize is not None
        self.assertEqual(initialize["result"]["serverInfo"]["name"], "agent-log-analysis-mcp")
        tools = await server.handle_request(_request("2", "tools/list", {}))
        assert tools is not None
        names = {item["name"] for item in tools["result"]["tools"]}
        self.assertEqual(
            names,
            {
                "get_event",
                "query_agent_events",
                "get_agent_timeline",
                "get_agent_correlation_chain",
                "aggregate_agent_events",
                "get_agent_raw_logs",
            },
        )

    async def test_tools_call_get_event(self) -> None:
        runtime = _FakeRuntime()
        server = AgentLogAnalysisMCPServer(runtime=runtime)
        response = await server.handle_request(
            _request("3", "tools/call", {"name": "get_event", "arguments": {"event_id": "evt-1"}})
        )
        response = _require_surface_response(response)
        self.assertEqual(runtime.calls, [("get_event", "evt-1")])
        event = _nested_map(
            _nested_map(_nested_map(response, "result"), "structuredContent"), "event"
        )
        self.assertEqual(event["event_id"], "evt-1")

    async def test_tools_call_query_agent_events(self) -> None:
        runtime = _FakeRuntime()
        server = AgentLogAnalysisMCPServer(runtime=runtime)
        arguments = {"agent_slug": "agent-a", "limit": 2}
        response = await server.handle_request(
            _request("4", "tools/call", {"name": "query_agent_events", "arguments": arguments})
        )
        response = _require_surface_response(response)
        self.assertEqual(runtime.calls, [("query_agent_events", arguments)])
        structured = _nested_map(_nested_map(response, "result"), "structuredContent")
        self.assertEqual(structured["agent_slug"], "agent-a")

    async def test_tools_call_get_agent_timeline(self) -> None:
        runtime = _FakeRuntime()
        server = AgentLogAnalysisMCPServer(runtime=runtime)
        arguments = {"agent_slug": "agent-a", "limit": 2}
        response = await server.handle_request(
            _request("4b", "tools/call", {"name": "get_agent_timeline", "arguments": arguments})
        )
        response = _require_surface_response(response)
        self.assertEqual(runtime.calls, [("get_agent_timeline", arguments)])
        structured = _nested_map(_nested_map(response, "result"), "structuredContent")
        self.assertEqual(structured["agent_slug"], "agent-a")

    async def test_tools_call_get_agent_correlation_chain(self) -> None:
        runtime = _FakeRuntime()
        server = AgentLogAnalysisMCPServer(runtime=runtime)
        arguments = {"agent_slug": "agent-a", "correlation_id": "corr-1"}
        response = await server.handle_request(
            _request(
                "4c",
                "tools/call",
                {"name": "get_agent_correlation_chain", "arguments": arguments},
            )
        )
        response = _require_surface_response(response)
        self.assertEqual(runtime.calls, [("get_agent_correlation_chain", arguments)])
        structured = _nested_map(_nested_map(response, "result"), "structuredContent")
        self.assertEqual(structured["correlation_id"], "corr-1")

    async def test_tools_call_aggregate_agent_events(self) -> None:
        runtime = _FakeRuntime()
        server = AgentLogAnalysisMCPServer(runtime=runtime)
        arguments = {"agent_slug": "agent-a", "group_by": ["status"]}
        response = await server.handle_request(
            _request(
                "4d",
                "tools/call",
                {"name": "aggregate_agent_events", "arguments": arguments},
            )
        )
        response = _require_surface_response(response)
        self.assertEqual(runtime.calls, [("aggregate_agent_events", arguments)])
        structured = _nested_map(_nested_map(response, "result"), "structuredContent")
        self.assertEqual(structured["agent_slug"], "agent-a")

    async def test_tools_call_get_agent_raw_logs(self) -> None:
        runtime = _FakeRuntime()
        server = AgentLogAnalysisMCPServer(runtime=runtime)
        arguments = {"agent_slug": "agent-a", "limit": 2}
        response = await server.handle_request(
            _request(
                "4e",
                "tools/call",
                {"name": "get_agent_raw_logs", "arguments": arguments},
            )
        )
        response = _require_surface_response(response)
        self.assertEqual(runtime.calls, [("get_agent_raw_logs", arguments)])
        structured = _nested_map(_nested_map(response, "result"), "structuredContent")
        self.assertEqual(structured["agent_slug"], "agent-a")


class TestMCPServerErrors(unittest.IsolatedAsyncioTestCase):
    """Verify MCP server error and notification handling."""

    async def test_notification_returns_none(self) -> None:
        server = AgentLogAnalysisMCPServer(runtime=_FakeRuntime())
        response = await server.handle_request(
            {"jsonrpc": "2.0", "method": "tools/list", "params": {}}
        )
        self.assertIsNone(response)

    async def test_invalid_method_returns_error(self) -> None:
        server = AgentLogAnalysisMCPServer(runtime=_FakeRuntime())
        response = await server.handle_request({"jsonrpc": "2.0", "id": "5", "params": {}})
        response = _require_error_response(response)
        error = _nested_map(response, "error")
        self.assertEqual(error["code"], -32600)

    async def test_unknown_tool_returns_error(self) -> None:
        server = AgentLogAnalysisMCPServer(runtime=_FakeRuntime())
        response = await server.handle_request(
            _request("6", "tools/call", {"name": "unknown_tool", "arguments": {}})
        )
        response = _require_error_response(response)
        error = _nested_map(response, "error")
        self.assertEqual(error["code"], -32000)
        self.assertIn("Unknown tool", str(error["message"]))

    async def test_validation_error_preserves_error_data(self) -> None:
        runtime = _FakeRuntime(
            error=ValidationError("AGENT_SCOPE_REQUIRED", "agent_slug is required")
        )
        server = AgentLogAnalysisMCPServer(runtime=runtime)
        response = await server.handle_request(
            _request("7", "tools/call", {"name": "query_agent_events", "arguments": {}})
        )
        response = _require_error_response(response)
        error = _nested_map(response, "error")
        error_data = _nested_map(error, "data")
        self.assertEqual(error_data["error_code"], "AGENT_SCOPE_REQUIRED")
        self.assertEqual(error_data["message"], "agent_slug is required")


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

    async def get_agent_timeline(self, payload: object) -> dict[str, object]:
        if self.error is not None:
            raise self.error
        self.calls.append(("get_agent_timeline", payload))
        return {
            "agent_slug": "agent-a",
            "window_start": "2025-01-01T00:00:00Z",
            "window_end": "2025-01-01T01:00:00Z",
            "items": [],
            "next_cursor": None,
        }

    async def get_agent_correlation_chain(self, payload: object) -> dict[str, object]:
        if self.error is not None:
            raise self.error
        self.calls.append(("get_agent_correlation_chain", payload))
        return {
            "agent_slug": "agent-a",
            "correlation_id": "corr-1",
            "items": [],
            "truncated": False,
        }

    async def aggregate_agent_events(self, payload: object) -> dict[str, object]:
        if self.error is not None:
            raise self.error
        self.calls.append(("aggregate_agent_events", payload))
        return {
            "agent_slug": "agent-a",
            "window_start": "2025-01-01T00:00:00Z",
            "window_end": "2025-01-01T01:00:00Z",
            "group_by": ["status"],
            "metrics": ["count"],
            "buckets": [{"keys": {"status": "success"}, "count": 1}],
        }

    async def get_agent_raw_logs(self, payload: object) -> dict[str, object]:
        if self.error is not None:
            raise self.error
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


def _request(request_id: str, method: str, params: REQUEST_MAP) -> REQUEST_MAP:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params,
    }


def _require_surface_response(response: REQUEST_MAP | None) -> dict[str, object]:
    assert response is not None
    return response


def _require_error_response(response: REQUEST_MAP | None) -> dict[str, object]:
    assert response is not None
    return response


def _nested_map(value: dict[str, object], key: str) -> dict[str, object]:
    nested = value.get(key)
    return nested if isinstance(nested, dict) else {}
