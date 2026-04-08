"""JSON-RPC method dispatch for Telegram MCP server."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from telegram_mcp.mcp_payloads import (
    resource_templates_result,
    resources_result,
    tools_result,
)
from telegram_mcp.mcp_protocol import (
    JsonDict,
    initialize_result,
    jsonrpc_error,
    jsonrpc_result,
    mcp_content,
)
from telegram_mcp.mcp_send import safe_handle_send

if TYPE_CHECKING:
    from telegram_mcp.mcp_server import TelegramMCPServer

logger = logging.getLogger(__name__)


async def dispatch_request(
    server: TelegramMCPServer,
    request: JsonDict,
) -> JsonDict | None:
    """Route a single JSON-RPC request to the correct handler."""
    if not isinstance(request, dict):
        return jsonrpc_error(None, -32600, "Invalid request")
    request_id = request.get("id")
    if request_id is None:
        return None
    try:
        return await _route(server, request, request_id)
    except Exception as exc:
        logger.error("MCP request failed: %s", exc, exc_info=True)
        return jsonrpc_error(request_id, -32000, str(exc))


async def _route(
    server: TelegramMCPServer,
    request: JsonDict,
    request_id: object,
) -> JsonDict:
    method = str(request.get("method") or "")
    simple = _simple_result(method)
    if simple is not None:
        return jsonrpc_result(request_id, simple)
    if method == "tools/call":
        params = request.get("params", {})
        safe = params if isinstance(params, dict) else {}
        result = await _dispatch_tool(server, safe)
        return jsonrpc_result(request_id, result)
    return jsonrpc_error(request_id, -32601, f"Method not found: {method}")


def _simple_result(method: str) -> JsonDict | None:
    if method == "initialize":
        return initialize_result()
    if method == "resources/list":
        return resources_result()
    if method == "resources/templates/list":
        return resource_templates_result()
    if method == "tools/list":
        return tools_result()
    return None


async def _dispatch_tool(
    server: TelegramMCPServer,
    params: JsonDict,
) -> JsonDict:
    name = str(params.get("name") or "")
    arguments = params.get("arguments")
    args: JsonDict = arguments if isinstance(arguments, dict) else {}
    if name == "send_telegram_message":
        return await safe_handle_send(server, args)
    return mcp_content({"ok": False, "error": f"Unknown tool: {name}"})
