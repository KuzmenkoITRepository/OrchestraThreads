from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from telegram_bot_mcp.mcp.protocol import JsonDict, Payloads, ServerHelpers
from telegram_bot_mcp.mcp.tool_dispatch import handle_tool_call

if TYPE_CHECKING:
    from telegram_bot_mcp.mcp.server import TelegramBotMCPServer

logger = logging.getLogger(__name__)


async def dispatch_request(
    server: TelegramBotMCPServer,
    request: JsonDict,
) -> JsonDict | None:
    request_id = request.get("id")
    if request_id is None:
        return None
    try:
        return await _route_request(server, request, request_id)
    except Exception as exc:
        logger.error("MCP request failed: %s", exc, exc_info=True)
        return ServerHelpers.jsonrpc_error(request_id, -32000, str(exc))


async def _route_request(
    server: TelegramBotMCPServer,
    request: JsonDict,
    request_id: Any,
) -> JsonDict:
    method = request.get("method")
    params = request.get("params", {})
    handler = _simple_handlers().get(str(method))
    if handler is not None:
        return ServerHelpers.jsonrpc_result(request_id, handler())
    if method == "tools/call":
        result = await handle_tool_call(
            server,
            name=str(params.get("name") or ""),
            arguments=ServerHelpers.request_arguments(params),
        )
        return ServerHelpers.jsonrpc_result(request_id, result)
    return ServerHelpers.jsonrpc_error(request_id, -32601, f"Method not found: {method}")


def _simple_handlers() -> dict[str, Any]:
    return {
        "initialize": ServerHelpers.initialize_result,
        "resources/list": ServerHelpers.resources_result,
        "resources/templates/list": ServerHelpers.resource_templates_result,
        "tools/list": Payloads.tools_result,
    }
