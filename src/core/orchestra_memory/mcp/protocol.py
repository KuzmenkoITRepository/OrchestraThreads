from __future__ import annotations

from typing import Any

from core.orchestra_memory.mcp.tool_specs import list_memory_tools
from core.orchestra_memory.mcp.tools import (
    memory_clear,
    memory_delete,
    memory_list_categories,
    memory_list_rooms,
    memory_remember,
    memory_search,
)
from core.orchestra_memory.mcp.tools_common import JSON_MAP

TOOL_HANDLER_ITEMS = (
    ("memory_remember", memory_remember),
    ("memory_search", memory_search),
    ("memory_delete", memory_delete),
    ("memory_clear", memory_clear),
    ("memory_list_rooms", memory_list_rooms),
    ("memory_list_categories", memory_list_categories),
)


def list_tools() -> list[JSON_MAP]:
    return list_memory_tools()


async def handle_tools_call(server: Any, *, name: str, arguments: JSON_MAP) -> JSON_MAP:
    handlers = dict(TOOL_HANDLER_ITEMS)
    handler = handlers.get(name)
    if handler is None:
        raise RuntimeError(f"Unknown tool: {name}")
    return await handler(server, arguments)


def extract_tool_call(params: JSON_MAP) -> tuple[str, JSON_MAP]:
    arguments = params.get("arguments")
    name = str(params.get("name") or "")
    if isinstance(arguments, dict):
        return name, arguments
    return name, {}


async def tool_call_result(server: Any, request_id: object, params: JSON_MAP) -> JSON_MAP:
    name, arguments = extract_tool_call(params)
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": await handle_tools_call(server, name=name, arguments=arguments),
    }


def error_response(request_id: object, code: int, message: str) -> JSON_MAP:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


async def resolve_method(
    server: Any,
    *,
    method: str,
    request_id: object,
    params: JSON_MAP,
) -> JSON_MAP:
    method_handlers: dict[str, JSON_MAP] = {
        "initialize": {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": server.handle_initialize(params),
        },
        "resources/list": {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"resources": []},
        },
        "resources/templates/list": {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"resourceTemplates": []},
        },
        "tools/list": {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": server.handle_tools_list(),
        },
    }
    if method == "tools/call":
        return await tool_call_result(server, request_id, params)
    handler_response = method_handlers.get(method)
    if handler_response is not None:
        return handler_response
    return error_response(request_id, -32601, f"Method not found: {method}")


async def resolve_request(server: Any, *, request: JSON_MAP, logger: Any) -> JSON_MAP | None:
    request_id = request.get("id")
    if request_id is None:
        return None
    raw_params = request.get("params")
    params: JSON_MAP = raw_params if isinstance(raw_params, dict) else {}
    try:
        return await resolve_method(
            server,
            method=str(request.get("method") or ""),
            request_id=request_id,
            params=params,
        )
    except Exception as exc:
        logger.error("MCP tool failed: %s", exc, exc_info=True)
        return error_response(request_id, -32000, str(exc))
