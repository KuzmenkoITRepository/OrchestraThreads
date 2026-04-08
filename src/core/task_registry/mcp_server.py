from __future__ import annotations

import json
import logging
import os
from typing import Any

from core.task_registry import mcp_server_support
from core.task_registry.config import load_config
from core.task_registry.mcp_tool_payloads import JsonDict
from core.task_registry.mcp_tool_specs import tool_specs
from core.task_registry.mcp_tools import TaskRegistryTools
from core.task_registry.store import TaskStore

logger = logging.getLogger(__name__)


async def _serve_loop(server: TaskRegistryMCPServer) -> None:
    while True:
        try:
            request = await mcp_server_support.read_request()
        except json.JSONDecodeError as exc:
            logger.error("Invalid JSON received: %s", exc)
            await mcp_server_support.write_response(
                mcp_server_support.jsonrpc_error(
                    None,
                    mcp_server_support.PARSE_ERROR_CODE,
                    "Parse error",
                )
            )
            continue

        if request is None:
            return

        response = await server.handle_request(request)
        if response is not None:
            await mcp_server_support.write_response(response)


async def _dispatch_request(
    server: TaskRegistryMCPServer,
    request_id: Any,  # noqa: ANN401
    method: str,
    request_params: Any,  # noqa: ANN401
) -> JsonDict | None:
    if method == "initialize":
        return mcp_server_support.jsonrpc_result(
            request_id,
            {
                "protocolVersion": mcp_server_support.PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": mcp_server_support.SERVER_NAME, "version": "0.1.0"},
            },
        )
    if method == "tools/list":
        return mcp_server_support.jsonrpc_result(request_id, {"tools": tool_specs()})
    if method == "tools/call":
        return await _handle_tools_call(server, request_id, request_params)
    if request_id is None:
        return None
    return mcp_server_support.jsonrpc_error(
        request_id,
        mcp_server_support.METHOD_NOT_FOUND_CODE,
        f"Method not found: {method}",
    )


async def _handle_tools_call(
    server: TaskRegistryMCPServer,
    request_id: Any,  # noqa: ANN401
    request_params: Any,  # noqa: ANN401
) -> JsonDict:
    await server.ensure_started()
    tool_name = mcp_server_support.extract_tool_name(request_params)
    arguments = mcp_server_support.request_arguments(request_params)
    tool_result = await server.tools.dispatch(tool_name, arguments)
    return mcp_server_support.jsonrpc_result(request_id, tool_result)


class TaskRegistryMCPServer:
    def __init__(self, store: TaskStore) -> None:
        self._store = store
        self._tools = TaskRegistryTools(store)
        self._started = False

    @property
    def tools(self) -> TaskRegistryTools:
        return self._tools

    async def handle_request(self, request: JsonDict) -> JsonDict | None:
        if not isinstance(request, dict):
            return mcp_server_support.jsonrpc_error(
                None,
                mcp_server_support.INVALID_REQUEST_CODE,
                "Invalid Request",
            )

        request_id = request.get("id")
        method = request.get("method")
        if not isinstance(method, str) or not method:
            return mcp_server_support.jsonrpc_error(
                request_id,
                mcp_server_support.INVALID_REQUEST_CODE,
                "Invalid Request",
            )

        try:
            return await _dispatch_request(self, request_id, method, request.get("params", {}))
        except Exception:
            logger.exception("Request handling failed")
            return mcp_server_support.jsonrpc_error(
                request_id,
                mcp_server_support.INTERNAL_ERROR_CODE,
                "Internal error",
            )

    async def serve(self) -> None:
        try:
            await _serve_loop(self)
        except Exception:
            logger.exception("MCP serve loop error")
        finally:
            await self.close()

    async def close(self) -> None:
        if not self._started:
            return
        await self._store.close()
        self._started = False

    async def ensure_started(self) -> None:
        if self._started:
            return
        await self._store.start()
        self._started = True


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = load_config()
    store = TaskStore(database_url=config.database_url)
    try:
        _run_server(store)
    except KeyboardInterrupt:
        logger.info("Task registry MCP server stopped")


def _run_server(store: TaskStore) -> None:
    import asyncio

    asyncio.run(TaskRegistryMCPServer(store).serve())


if __name__ == "__main__":
    main()
