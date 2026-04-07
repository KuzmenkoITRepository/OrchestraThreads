from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any

from core.orchestra_thread.mcp_transport import encode_message, read_message
from environment_mcp.command_runner import CommandRunner
from environment_mcp.config import EnvironmentMCPConfig, load_config
from environment_mcp.mcp_protocol import Payloads, ServerHelpers
from environment_mcp.tools import EnvironmentTools

logger = logging.getLogger(__name__)


class EnvironmentMCPServer:
    def __init__(self, *, config: EnvironmentMCPConfig | None = None, runner: Any = None) -> None:
        self.config = config or load_config()
        self.tools = EnvironmentTools(self.config, runner or CommandRunner())

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any] | None:
        request_id = request.get("id")
        if request_id is None:
            return None
        try:
            return await self._dispatch_request(request, request_id)
        except Exception as exc:
            logger.error("MCP request failed: %s", exc, exc_info=True)
            return ServerHelpers.jsonrpc_error(request_id, -32000, str(exc))

    async def handle_tools_call(self, *, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        handlers = _tool_handlers(self.tools)
        handler = handlers.get(name)
        if handler is None:
            return Payloads.result({"ok": False, "error": f"Unknown tool: {name}"})
        payload = await handler(arguments)
        text = str(payload.pop("text", "")).strip() or None
        return Payloads.result(payload, text=text)

    async def _dispatch_request(
        self, request: dict[str, Any], request_id: object
    ) -> dict[str, Any]:
        method = request.get("method")
        params = request.get("params", {})
        handler = _simple_handlers().get(str(method))
        if handler is not None:
            return ServerHelpers.jsonrpc_result(request_id, handler())
        if method == "tools/call":
            result = await self.handle_tools_call(
                name=str(params.get("name") or ""),
                arguments=ServerHelpers.request_arguments(params),
            )
            return ServerHelpers.jsonrpc_result(request_id, result)
        return ServerHelpers.jsonrpc_error(request_id, -32601, f"Method not found: {method}")


def main() -> None:
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(_main_async())


async def _main_async() -> None:
    server = EnvironmentMCPServer()
    await _serve_requests(server)


async def _serve_requests(server: EnvironmentMCPServer) -> None:
    framing: str | None = None
    while True:
        request, framing = await read_message(sys.stdin.buffer, framing_hint=framing)
        if request is None:
            return
        response = await server.handle_request(request)
        if response is None:
            continue
        sys.stdout.buffer.write(encode_message(response, framing=framing or "newline"))
        sys.stdout.buffer.flush()


def _simple_handlers() -> dict[str, Any]:
    return {
        "initialize": ServerHelpers.initialize_result,
        "resources/list": ServerHelpers.resources_result,
        "resources/templates/list": ServerHelpers.resource_templates_result,
        "tools/list": Payloads.tools_result,
    }


def _tool_handlers(tools: EnvironmentTools) -> dict[str, Any]:
    return {
        "environment_list": tools.environment_list,
        "environment_status": tools.environment_status,
        "environment_create": tools.environment_create,
        "environment_deploy": tools.environment_deploy,
        "environment_teardown": tools.environment_teardown,
        "environment_usage_guide": tools.environment_usage_guide,
    }
