"""JSON-RPC protocol helpers for the agent-log-analysis MCP surface."""

from __future__ import annotations

from importlib import import_module
from typing import Any, Protocol, cast

from core.agent_log_analysis.errors import EventNotFoundError, ValidationError
from core.agent_log_analysis.mcp.tools.events import handle_tools_call as handle_event_tools_call

JSON_MAP = dict[str, Any]
PROTOCOL_VERSION = "2024-11-05"
INVALID_REQUEST_CODE = -32600


class _RuntimeProtocol(Protocol):
    async def get_event(self, event_id: str) -> JSON_MAP: ...

    async def query_agent_events(self, payload: object) -> JSON_MAP: ...

    async def get_agent_timeline(self, payload: object) -> JSON_MAP: ...

    async def get_agent_correlation_chain(self, payload: object) -> JSON_MAP: ...

    async def aggregate_agent_events(self, payload: object) -> JSON_MAP: ...

    async def get_agent_raw_logs(self, payload: object) -> JSON_MAP: ...


class _ServerProtocol(Protocol):
    def handle_initialize(self, params: JSON_MAP) -> JSON_MAP: ...

    def handle_tools_list(self) -> JSON_MAP: ...

    @property
    def runtime(self) -> _RuntimeProtocol: ...


class MCPProtocol:
    """Small JSON-RPC resolver and tool catalog."""

    jsonrpc_version = "2.0"
    method_not_found_code = -32601
    internal_error_code = -32000

    @classmethod
    async def resolve_request(
        cls,
        server: _ServerProtocol,
        *,
        request: JSON_MAP,
        logger: Any,
    ) -> JSON_MAP | None:
        request_id = request.get("id")
        if request_id is None:
            return None
        raw_params = request.get("params")
        params: JSON_MAP = raw_params if isinstance(raw_params, dict) else {}
        try:
            return await cls._resolve_method(
                server,
                request_id=request_id,
                method=str(request.get("method") or ""),
                params=params,
            )
        except Exception as exc:
            logger.error("MCP tool failed: %s", exc, exc_info=True)
            return cls._error_from_exception(request_id, exc)

    @classmethod
    def error_response(
        cls,
        request_id: object,
        code: int,
        message: str,
        *,
        data: JSON_MAP | None = None,
    ) -> JSON_MAP:
        error: JSON_MAP = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        return {
            "jsonrpc": cls.jsonrpc_version,
            "id": request_id,
            "error": error,
        }

    @classmethod
    def jsonrpc_result(cls, request_id: object, result_payload: JSON_MAP) -> JSON_MAP:
        return {
            "jsonrpc": cls.jsonrpc_version,
            "id": request_id,
            "result": result_payload,
        }

    @classmethod
    async def _resolve_method(
        cls,
        server: _ServerProtocol,
        *,
        request_id: object,
        method: str,
        params: JSON_MAP,
    ) -> JSON_MAP:
        response = cls._static_method_response(
            server,
            request_id=request_id,
            method=method,
            params=params,
        )
        if response is not None:
            return response
        if method == "tools/call":
            name, arguments = extract_tool_call(params)
            result_payload = await cls._handle_tool_call(
                server.runtime,
                name=name,
                arguments=arguments,
            )
            return cls.jsonrpc_result(request_id, result_payload)
        return cls.error_response(
            request_id,
            cls.method_not_found_code,
            f"Method not found: {method}",
        )

    @classmethod
    def _static_method_response(
        cls,
        server: _ServerProtocol,
        *,
        request_id: object,
        method: str,
        params: JSON_MAP,
    ) -> JSON_MAP | None:
        if method == "initialize":
            return cls.jsonrpc_result(request_id, server.handle_initialize(params))
        if method == "resources/list":
            return cls.jsonrpc_result(request_id, {"resources": []})
        if method == "resources/templates/list":
            return cls.jsonrpc_result(request_id, {"resourceTemplates": []})
        if method == "tools/list":
            return cls.jsonrpc_result(request_id, server.handle_tools_list())
        return None

    @classmethod
    def _error_from_exception(cls, request_id: object, exc: Exception) -> JSON_MAP:
        if isinstance(exc, ValidationError):
            return cls.error_response(
                request_id,
                cls.internal_error_code,
                exc.message,
                data={"error_code": exc.error_code, "message": exc.message},
            )
        if isinstance(exc, EventNotFoundError):
            message = str(exc)
            return cls.error_response(
                request_id,
                cls.internal_error_code,
                message,
                data={"error_code": "EVENT_NOT_FOUND", "message": message},
            )
        return cls.error_response(request_id, cls.internal_error_code, str(exc))

    @classmethod
    async def _handle_tool_call(
        cls,
        runtime: _RuntimeProtocol,
        *,
        name: str,
        arguments: JSON_MAP,
    ) -> JSON_MAP:
        if name in {"get_event", "query_agent_events"}:
            return await handle_event_tools_call(runtime, name=name, arguments=arguments)
        if name in {"aggregate_agent_events", "get_agent_raw_logs"}:
            module_name = "core.agent_log_analysis.mcp.tools.aggregates"
            if name == "get_agent_raw_logs":
                module_name = "core.agent_log_analysis.mcp.tools.raw_logs"
            tool_module = import_module(module_name)
            tool_handler = cast(Any, getattr(tool_module, name))
            return cast(JSON_MAP, await tool_handler(runtime, arguments))
        if name not in {"get_agent_timeline", "get_agent_correlation_chain"}:
            raise RuntimeError(f"Unknown tool: {name}")
        timeline_module = import_module("core.agent_log_analysis.mcp.tools.timeline")
        tool_handler = cast(Any, getattr(timeline_module, name))
        return cast(JSON_MAP, await tool_handler(runtime, arguments))


def list_tools() -> list[JSON_MAP]:
    """Return MCP tool metadata for the current MCP surface."""
    return [
        {
            "name": "get_event",
            "description": "Look up one event by event_id.",
            "inputSchema": {
                "type": "object",
                "properties": {"event_id": _string_schema()},
                "required": ["event_id"],
            },
        },
        {
            "name": "query_agent_events",
            "description": "Query agent-scoped events with required agent_slug and bounded window/page parameters.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "agent_slug": _string_schema(),
                    "window_start": _string_schema(),
                    "window_end": _string_schema(),
                    "run_id": _string_schema(),
                    "thread_id": _string_schema(),
                    "correlation_id": _string_schema(),
                    "event_type": _string_schema(),
                    "status": _string_schema(),
                    "request_kind": _string_schema(),
                    "action_kind": _string_schema(),
                    "target_name": _string_schema(),
                    "target_agent_slug": _string_schema(),
                    "provider_name": _string_schema(),
                    "model_name": _string_schema(),
                    "cursor": _string_schema(),
                    "limit": {"type": "integer"},
                    "labels": {
                        "type": "object",
                        "additionalProperties": _string_schema(),
                    },
                },
                "required": ["agent_slug"],
            },
        },
        {
            "name": "get_agent_timeline",
            "description": "Query newest-first agent timeline pages with required agent_slug and bounded window/page parameters.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "agent_slug": _string_schema(),
                    "window_start": _string_schema(),
                    "window_end": _string_schema(),
                    "run_id": _string_schema(),
                    "thread_id": _string_schema(),
                    "cursor": _string_schema(),
                    "limit": {"type": "integer"},
                },
                "required": ["agent_slug"],
            },
        },
        {
            "name": "get_agent_correlation_chain",
            "description": "Query oldest-first agent-scoped correlation chains with required agent_slug and correlation_id.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "agent_slug": _string_schema(),
                    "correlation_id": _string_schema(),
                    "run_id": _string_schema(),
                    "thread_id": _string_schema(),
                },
                "required": ["agent_slug", "correlation_id"],
            },
        },
        {
            "name": "aggregate_agent_events",
            "description": "Query bounded aggregate buckets with required agent_slug and validated grouping/metric parameters.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "agent_slug": _string_schema(),
                    "window_start": _string_schema(),
                    "window_end": _string_schema(),
                    "group_by": {
                        "type": "array",
                        "items": _string_schema(),
                    },
                    "metrics": {
                        "type": "array",
                        "items": _string_schema(),
                    },
                },
                "required": ["agent_slug"],
            },
        },
        {
            "name": "get_agent_raw_logs",
            "description": "Query exact paginated raw logs with required agent_slug and bounded window/page parameters.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "agent_slug": _string_schema(),
                    "window_start": _string_schema(),
                    "window_end": _string_schema(),
                    "run_id": _string_schema(),
                    "thread_id": _string_schema(),
                    "correlation_id": _string_schema(),
                    "event_id": _string_schema(),
                    "level": _string_schema(),
                    "source": _string_schema(),
                    "cursor": _string_schema(),
                    "limit": {"type": "integer"},
                },
                "required": ["agent_slug"],
            },
        },
    ]


def extract_tool_call(params: JSON_MAP) -> tuple[str, JSON_MAP]:
    """Extract tool name and arguments from tools/call params."""
    name = str(params.get("name") or "")
    arguments = params.get("arguments")
    if isinstance(arguments, dict):
        return name, arguments
    return name, {}


def _string_schema() -> JSON_MAP:
    return {"type": "string"}
